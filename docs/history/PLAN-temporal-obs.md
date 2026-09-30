# Observation v2: fixed-Δt film-strip frames (added after S2, 2026-08)

> Background: S2 showed that "blockage perception" depended entirely on the harness-injected
> `[you were BLOCKED]` text (zero detections without it in v1), and that the action-boundary
> single-frame observation cannot in principle capture purely temporal bugs (animation/light
> anomalies). This plan shifts observation from action-centric to **time-centric**.

## Design

**Film strip**: during every action (including `wait`), low-res frames are sampled at a fixed
sim-clock interval and attached to that step's message; `interact`'s hand-tuned three frames
(t0/0.7s/2.8s) are subsumed by this mechanism.

| Param | Default | Notes |
|---|---|---|
| `filmDt` | 0.3 s | sampling interval (sim time). At 5.2 m/s walking speed ⇒ ~1.6 m between frames |
| `filmMaxFrames` | 8 | per-action cap; longer actions sample evenly, **every frame carries a t=+X.Xs timestamp** so the temporal ruler stays explicit even when the stride stretches |
| `filmRes` | 480×300 | film-frame resolution (the final frame stays 960×600) |

**Token budget** (Qwen3-VL, 32k context, long-horizon constraint):
- 960×600 ≈ 350–700 tok/frame; 480×300 ≈ 90–180 tok/frame
- Per step: 7 low-res + 1 full-res ≈ 1.2–1.9k tok
- Rolling window shrinks: only the current step carries the strip; the previous 1–2 steps keep a
  low-res final frame; older steps become text. Per-step image budget ≈ 2–2.5k tok, constant
  over a 200-step episode.
- Resolution/Δt/window are linked knobs, all parameterized as ablation axes.

**Companion changes**:
1. In film mode, blocked moves no longer early-abort on stall: the evidence for blockage is
   precisely "pushing forward while the view stays frozen" (the deadline backstop remains).
2. `blocked_hint` split out of proprio into its own switch: the ablation matrix needs the
   "position text on + blocked hint off" cell (v1's proprio=0 removed both at once, confounding
   attribution).
3. `wait` upgraded to a sensing action; the audit prompt notes that "some bugs only show over
   time - standing still and observing is a valid test".
4. New bug type `frozen_anim` (freeze a target object's animation updater — torch flame /
   gem spin), since the registry lacked a purely temporal ambient bug to test this channel.
   Implementation: updaters are registered per owner id (`ctx.addUpdater(id, fn)`), and the bug
   suspends them by id.
5. New envs `env2-temporal-bug/clean`: a torch pair (one frozen / both normal), matched control,
   tasks `audit_torch_*`.

## Ablation matrix (S2v2; 30B-A3B primary; 10 seeds/cell)

| Axis | Values |
|---|---|
| bug | air wall (movement class) · frozen torch (temporal class) · each with matched clean control |
| observation | single (v1 single-frame) · film (strip) |
| hint | blocked_hint off (primary) · on (reference, reusing v1 data) |

**Criteria**:
- film + no-hint air-wall detection ≈ or ≥ the v1 "single + hint" level (6–7/10) with clean FP
  not worse ⇒ blockage perception has moved from injected aid to genuine perception;
- frozen torch: film detection > 0 and significantly above control, single ≈ 0 ⇒ the temporal
  channel has independent value.

**Outcome (see EXPERIMENTS.md)**: neither criterion was met. The decisive channel for 30B
turned out to be the proprio *number* (`moved 0.00m`), not the hint text; film strips raised
clean FP without raising detection; the frozen torch went undetected in-loop in both arms even
though a focused single query reads the asymmetry from the same frames — locating the bottleneck
at the agency layer (models do not spontaneously perform the comparison), with a secondary
spatial-binding failure (left/right swapped when they do read it).

**Explicit non-goal**: minute-scale slow drifts (e.g. gradually shifting sun angle) exceed a
single step's strip; they belong to the cross-step memory problem (S3 investigation notes), not
this plan.

## Compatibility

Off by default (single mode) — v1's S1/S2 results and cross-model comparability are unaffected;
film mode is enabled explicitly via `runner --obs film`.
