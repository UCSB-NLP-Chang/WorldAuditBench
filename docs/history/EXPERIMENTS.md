# Experiment Log & Results

Living document. Records every experiment stage, per-model and per-category results, and the
methodology decisions behind them. Environments, harness and scoring: see `README.md`;
original research plan: `PLAN.md`; observation-v2 design: `PLAN-temporal-obs.md`.

**Models evaluated** (all served locally via vLLM 0.11.2, bf16, on 2×RTX A6000 unless noted):

| Model | Arch | Serving | Step latency |
|---|---|---|---|
| Qwen3-VL-4B-Instruct | dense | 1 GPU | ~1.0 s |
| Qwen3-VL-8B-Instruct | dense | 1 GPU | ~1.2 s |
| Qwen3-VL-30B-A3B-Instruct | MoE (3B active) | TP2 | ~1.4 s |
| Qwen3-VL-32B-Instruct | dense | TP2 | ~2.5 s |
| InternVL3_5-38B | dense | TP2, 12k ctx | multi-image prompts infeasible (>7 min/call); ran single-frame mode only |

Rendering: headless Chromium with native A6000 (`--use-angle=gl-egl`), 960×600, ~60 fps.
All timings on the environment's virtual sim clock (render-speed independent).

---

## S0 — Harness smoke test (scripted, no VLM)

env0 corridor; every action executed ≥20×; 35/35 checks PASS (yaw/pitch tracking <1.5°,
blocked detection with zero false positives, interact 3-frame timing, full door→lever→gate→ring
traversal, no JS errors, frames valid). Re-passed after the interaction-occlusion engine change.

## S1 — Navigation probe (env1 Sponza, 3 tasks × 10 seeds × proprio {off,on})

Success = final position within 3 m of target ring. `false_done` = model declared done outside
the radius. Single-frame observation; proprio = position/heading/moved text feedback.

| Task | Metric | 8B p0 | 8B p1 | 30B-A3B p0 | 30B-A3B p1 |
|---|---|---|---|---|---|
| ring_visible (servo) | SR | 40% | **100%** | 10% | 10% |
| | false_done | 6/10 | 0/10 | 9/10 | 9/10 |
| ring_search (turn & find) | SR | 50% | 70% | 40% | 30% |
| | false_done | 4/10 | 3/10 | 6/10 | 7/10 |
| ring_multi (2-stage) | SR | 0% | 0% | **30%** | **30%** |
| | false_done | 5/10 | 6/10 | 3/10 | 3/10 |

Gate (ring_visible SR ≥60%): **PASS for 8B+proprio (100%)**.

Findings: (1) 30B's ring_visible failures are all premature `done` at 3.0–5.5 m — arrival
mis-calibration ("ring visible at bottom of frame" ⇒ "standing on it"), not navigation failure;
SR is radius-sensitive. (2) Proprio's main effect is suppressing false dones (8B: 100%→40% when
removed). (3) 30B is the only model completing the 2-stage task; 8B collapses via color
misbinding (labels cyan ring "orange") and blocked-loop wandering. (4) Failure taxonomy:
color/object misbinding, arrival hallucination, post-blocking disorientation.

## S2 — Targeted bug audit (env2 Sponza; air wall L2 + floating crate L1; matched clean controls)

10 seeds/cell. Detection = flag within 3 m of the planted bug; clean FP = any flag in a clean
episode. Single-frame observation.

| Cell | 8B p0 | 8B p1 | 30B p0 | 30B p1 |
|---|---|---|---|---|
| Air-wall detection | 0/10 | 6/10 (loc 0.50 m) | 0/10 | **7/10** (loc 1.14 m) |
| East clean FP | 0/10 | 5/10 | 0/10 | 7/10 |
| Floating-crate detection | 0/10 | 1/10* | 0/10 | 0/10 |
| West clean FP | 0/10 | 2/10 | 0/10 | 0/10 |

*Later shown to be a misattributed collision flag that landed within radius; genuine float
recognition was 0/40.

Fisher gates (detection ≫ clean FP): **all FAIL**. With proprio off, zero flags in all 80
episodes. Clean-group FPs are dominated by misattributed collisions with visible obstacles
(fountain steps, columns) reported as "invisible wall".

### S2 v2 — Observation ablation (30B-A3B; position text on; blocked-hint OFF)

| Cell | single-frame | film-strip | (ref: single + hint, v1) |
|---|---|---|---|
| Air-wall detection | **6/10** | 5/10 | 7/10 |
| East clean FP | **3/10** | 7/10 | 7/10 |
| Frozen-torch detection | 0/10 | 0/10 | – |
| Torch clean FP | 0/10 | 0/10 | – |

Findings: (1) The BLOCKED text hint is *not* the key channel — the `moved 0.00m` number
suffices for 30B (v1's "0 detection without hint" conflated removing the hint with removing
position text). Removing the hint *improved* discrimination (FP 7→3). (2) Film strips did not
raise detection and doubled clean FP (more paranoid flagging). (3) Frozen torch: 0/10 in both
arms despite `wait` being used in 10/10 episodes — but a focused single query over the same
frames correctly reads "one flame animates, one static" (with left/right swapped). Three-layer
failure decomposition: sensing (partly works) / spatial binding (broken) / agency —
spontaneous verification (absent).

### Passive VQA probe (Track-P preview; 30B; 20 in-episode frames)

"Is there a bug in this frame?" — bug frames: 7/10 mention floating; **clean frames: 10/10
false positives** (hanging cauldrons/banners reported as floating bugs). Passive VQA = high
recall, zero specificity; embodied loop = low FP, low recall. Complementary failure modes.

## TC suite — 11 isolated bug/clean pairs × 5 models (taxonomy-grounded, environment-layer only)

Bugs per Butt et al. (2023) taxonomy, environment layer only. Film-strip observation,
blocked-hint off, proprio position text on, 5 seeds/cell (InternVL: single-frame, 3 seeds).
Scoring (canonical, 2026-08-29): a bug counts as **found** iff at least one emitted flag's
description is judged by an LLM judge (Qwen3-VL-30B, temp 0) to describe the planted defect.
**Flag position is not scored** - it is undefined for moving/global bugs and, as an eligibility
gate, it suppressed genuinely correct remote reports; it is kept only as an auxiliary
localization diagnostic. **Clean FP** = any flag in a clean episode.

### Per-case judge-based "found" (n=5 per cell; InternVL n=3)

| Case (category) | 4B | 8B | 30B-A3B | 32B | InternVL* |
|---|---|---|---|---|---|
| tc01 auto-closing door (temporal) | 0 | 0 | 0 | **5** | 0 |
| tc02 instant-open door (temporal) | 0 | 3 | 0 | **2** | 0 |
| tc03 half-stuck door (temporal) | 2 | 1 | 0 | **4** | 0 |
| tc04 self-drifting crate (temporal) | 0 | 0 | 0 | 0 | 0 |
| torch frozen flame (temporal) | 0 | 0 | 0 | **2** | 0 |
| tc05 wall trap (collision) | 0 | 0 | 0 | 0 | 0 |
| tc10 invisible obstacle (collision/render) | 1 | **5** | **5** | **5** | **3/3** |
| tc06 interact-through-barrier (interaction) | 0 | 0 | 0 | 0 | 1/3 |
| tc07 full-screen tint (rendering) | **5** | **5** | 2 | 3 | 0 |
| tc08 out-of-place asset (placement) | 0 | 0 | 0 | 0 | 0 |
| tc09 sunken crate (placement) | 0 | 0 | 0 | 0 | 0 |

Aux localization of matching flags (diagnostic): 32B averages 1.3-2.5m from the defect;
4B/8B's temporal detections come from ~6m away (they describe correctly but do not approach).
Full matrix with clean-FP columns: `reports/tc-night-0827/judge-matrix.md`.

### Per-category rollup (4 Qwen models pooled; judge-found / clean FP)

| Category | Found | Clean FP | Reading |
|---|---|---|---|
| Collision (invisible obstacle) | 16/20 (80%) | 3/20 | The one genuinely solved case: high detection AND low FP, cross-family (InternVL 3/3, 0 FP) |
| Rendering (tint) | 15/20 (75%) | **16/20** | High recall, high FP — small models flag it bug-or-not; only 32B discriminates (3/5 found vs 1/5 FP) |
| Temporal (5 cases) | 19/100 (19%) | 44/100 | 13 of 19 from 32B (only model covering the full family); 8B/4B add 6 remote door-animation reports; clean FPs dominated by door-operation-failure complaints |
| Placement (extra asset, sunken crate) | 0/40 (0%) | 16/40 | Models collide with the anomaly and flag at its location, but describe it as "invisible wall" 100% of the time — zero correct descriptions |
| Interaction (through-barrier) | 0/20 | 4/20 | Qwen never tests it; InternVL's 1/3 is instruction-primed false credit — it interacted from 5.8m (out of range), itself reported "no change", yet flagged through-barrier interaction anyway |
| Collision (wall trap) | 0/20 | 2/20 | Never triggered: 1/20 episodes entered the trap (models politely walk around) |

### Model totals — judge-found and detection-style P/R/F1

One planted bug per episode; TP = instance found (judge); surplus flags, duplicates and all
clean-episode flags are FP.

| Model | Found | Clean-FP episodes | P | R | F1 | Flags emitted |
|---|---|---|---|---|---|---|
| Qwen3-VL-4B | 8/55 | 29/55 | 0.01 | 0.15 | 0.03 | 554 |
| Qwen3-VL-8B | 14/55 | 25/55 | 0.04 | 0.25 | 0.07 | 335 |
| Qwen3-VL-30B-A3B | 7/55 | 9/55 | 0.05 | 0.13 | 0.08 | 128 |
| **Qwen3-VL-32B** | **21/55** | 22/55 | **0.12** | **0.38** | **0.19** | 169 |
| InternVL3_5-38B* | 4/33 | 6/33 | **0.16** | 0.12 | 0.14 | 25 |

*Single-frame observation, 3 seeds — different operating point (conservative flagger), not
strictly comparable on temporal cases. Note prevalence is 50% bug episodes; real-world
precision would be lower at realistic bug densities.

### TC-suite findings

1. **"Invisible wall" is the universal misattribution hammer**. Any collision — sunken
   crate, out-of-place gate, half-stuck door — gets reported as an invisible wall; placement
   bugs are reached and flagged at the right spot yet score 0/40 found.
2. **Full temporal-bug coverage emerges only at 32B dense** (auto-close 5/5, half-stuck 4/5,
   frozen flame 2/5, instant-open 2/5); 8B/4B partially detect the two door-animation cases
   from ~6m away without approaching (8B instant-open 3/5, 4B half-stuck 2/5); 30B-A3B MoE
   scores 0 across all temporal cases despite similar param count — dense vs MoE gap, not
   just scale.
3. **Mechanism operation is a prerequisite and is itself hard**: levers 0/40 across models
   (test cases redesigned to direct-interact doors); doors operable only by 32B (3/5) and
   30B (2/5). Failed operation produces spurious "unresponsive mechanism" reports.
4. **No proactive physical probing**: wall-trap entered in 1/20 episodes; through-barrier
   interaction never attempted at working range. These cells measure engagement, not
   perception. Corollary: the only judge-credited through-barrier "detection" (InternVL 1/3)
   is a verbal guess that contradicts the model's own observation ("the interaction did not
   result in any change ... this suggests interactions are not respecting the barrier") —
   description-matching judges can be gamed by instruction-primed guessing.
5. **Small models = high recall, zero discrimination** (4B: 554 flags, precision 0.01).
6. Self-drifting crate: 0/25 despite ~8 cm/frame inter-frame displacement present in the
   film strip — clearest "evidence in context, still unseen" temporal case.

## SP suite (v2, 2026-08-29) — Sponza-native bugs, turn-based world

Benchmark redesign per project review (see `reports/sp-suite/README.md` for the full case
table and screenshots):

1. **Environment realism**: all cases now live in the original Khronos Sponza atrium; bugs
   are mutations of the scene's own repeated elements (pots, drapes), so every case is
   unambiguous against the scene's internal consistency. Corridor TC cases and the ambiguous
   door bugs (auto-close, instant-open — defensible as intentional design) are retired.
2. **Taxonomy v2** (5 categories): geometry-space (4 cases), collision-physics (4),
   visual-consistency (3), spatiotemporal-state (3), semantics-logic (1) = 15 bug cases +
   1 shared clean config, uniform neutral patrol instruction, no per-case priming.
3. **Turn-based sim clock**: the world is frozen while the policy deliberates; time advances
   only inside action-execution windows at natural durations (walk = dist/speed, turn =
   deg/120°s, wait = ms). Removes the unobserved-time confound; enables the exact
   look-away-triggered spatiotemporal cases (despawn / teleport-when-unseen).
   Verified by `harness/pause_verify.py` (8/8).
4. **Soundness**: `harness/sp_verify.py` — 45/45 behavioral assertions pass (every bug
   demonstrably manifests; clean hall fully patrollable end to end).
5. Pipeline smoke (30B, 1 episode, sp09): full patrol + voluntary done; the flat-magenta
   drape filled ~1/3 of a frame mid-patrol and was not flagged — stimulus salience confirmed,
   detection is the measured variable.

### SP results (4 Qwen models; 15 bug cases x 3 resamples + clean x 6; judge v2, strict)

Scale note: the world is deterministic (fixed seed/spawn); the only stochasticity is policy
sampling at temperature 0.4, so per-case n=3 resamples (clean n=6 for the FP denominator).

| model | found /45 | clean FP eps /6 | P | R | F1 | flags |
|---|---|---|---|---|---|---|
| Qwen3-VL-4B | 0 | 0 | 0.00 | 0.00 | 0.00 | 40 |
| Qwen3-VL-8B | 2 | 1 | 0.02 | 0.04 | 0.02 | 121 |
| Qwen3-VL-30B-A3B | 1 | 0 | 0.17 | 0.02 | 0.04 | 6 |
| **Qwen3-VL-32B** | **5** | 0 | 0.16 | **0.11** | 0.13 | 31 |

Only 3 of 15 cases were ever found by anyone: sp05 air wall (32B 1/3, 8B 2/3, 30B 1/3),
sp06 fall-through floor (32B 1/3 — described as "moving forward resets position to start"),
sp09 magenta drape (32B 3/3). **The other 12 cases are 0 across every model**, including
every geometry-space case (floating/sunken/oversized/duplicated pot), every
spatiotemporal-state case, drift, x-ray, the redesigned ghost drape and backcull drape
(v2 cells rerun after the case redesigns - still 0: no agent pushes into drapes or goes
around the colonnade), and the out-of-place portcullis. Full matrix: `reports/sp-suite/judge-matrix.md`.

Engagement verification (zeros are perception failures, not missed encounters):
- sp12/13 look-away triggers FIRED in 24/24 episodes (offline gaze reconstruction from
  trajectories): the pot genuinely despawned/teleported in every episode; no model noticed.
- sp06: all 12 episodes actually fell through and respawned; only 32B verbalized it.
- Pots and drapes line the patrol route and appear in-frame throughout (see videos).

Key findings vs the corridor TC suite:
1. **The real environment collapses detection 3-4x**: 32B 21/55 (38%) on toy corridors ->
   5/45 (11%) on Sponza. Visual richness masks even screaming-obvious defects (a flat
   magenta drape is found only by 32B; a pot floating half a meter in the air by nobody).
2. **Flag volume collapses too** (30B: 128 -> 6 flags): in a plausible-looking scene models
   default to "intentional design" and barely flag at all; clean FP is near zero (1/24
   episodes) - the toy-world flag-spam problem largely disappears on its own.
3. **Embodied blockage remains the only reliably detected signal family** (air wall,
   fall-through), and only via proprio-position evidence; 32B alone converts the
   respawn-position jump into a correct bug description.
4. **"Invisible wall" misattribution persists in the real world**: agents repeatedly walk
   into the east-end lion fountain, read the stop as an invisible wall, and spam flags
   there (8B: 88 of its 111 flags; also its single clean FP). Judge v2 rejects all of them.
5. 4B saw the out-of-place portcullis in all 3 episodes but described it as "black vertical
   bars - likely rendering artifact" - detection without semantic binding.

Judge v2 (strict same-defect-type + same-object rule, cache `runs/judge_cache_v2.json`):
introduced after auditing v1 verdicts on this suite - v1 had granted 3 false credits
(generic invisible-wall notes matched to sp10's culled drape; a "floating basin"
misreading of the hanging braziers matched to sp07) and missed 2 true detections
(sp06 respawn-reset phrasing; a sp09 paraphrase). GT texts amended accordingly.

## Setting 2 (2026-08-30) — decoupled explorer/auditor with tiered accuracy

Design: a low-cost VLA game model (**Open-P2P 1.2B**, elefant-ai; 192x192 pixels -> 20Hz
keyboard+mouse, behavior-cloned on 8k hours of gameplay, MIT) explores each SP world with no
bug knowledge; the recording (full-res frame every 0.5s sim + poses + env event log) is then
audited by a strong VLM (Qwen3-VL-32B) via chunked video-VQA; claims are scored by the
strict v2 judge. Contrast with Setting 1, where one model both acts and audits.

Integration: `harness/p2p_server.py` (stdin/stdout JSONL around KVCacheInferenceState,
elefant_rust stubbed out - training-only), `harness/vla_explore.py` (continuous
`__env.tick(keys, mouse, 50ms)` drive; same paused-world clock; stuck-recovery wrapper:
2s of held-W with zero displacement -> back up + turn 120deg, alternating, logged),
`eval/vqa_audit.py` (VQA + tiered scoring).

**Tiered accuracy** (per case):
- Tier E (exposure): the bug observably manifested in the recording - per-case rules over
  the env event log (respawn / despawn_fired / teleport_fired / colorflip) and gaze
  geometry from recorded poses (view-cone + distance).
- Tier I|E (identification given exposure): >=1 VQA claim judge-matched to the planted bug.
- End-to-end found = E x I|E; clean-recording FP reported separately.
This formalizes the engagement-vs-perception decomposition used in Setting 1's audit.

Pilots: P2P walks with a real-game prior (holds W ~98% of ticks, 49-79m path in 60s sim,
covers the full hall and both aisles when sampling cooperates); failure mode = wall-grinding
at the west fountain corner (79% of one pilot episode) - hence the recovery wrapper.

Instruction-following ablation (3 arms, 20s sim each, same hall): no text -> 23m path /
17% W-held; "Explore this place..." -> 80m / 70%; "Stand completely still. Do not move." ->
46m / 24%. The text channel (a single 768-d embeddinggemma sentence vector) is real and
large as STYLE conditioning, but the model cannot execute constraints or negations - told
to stand still it walks 46m. Explorer = legs, not ears; directed auditing stays with the VLM.

### Setting 2 results (P2P-1.2B explorer x2/case, 32B VQA auditor, strict judge + event-time gate)

| tier | result |
|---|---|
| E exposure | **26/30 (87%)** - misses: ghost drape 0/2 (never crossed its plane), backcull drape 1/2, colorflip 1/2 (final, post sp07/sp10/sp12-13 redesign+reruns) |
| I given E | **3/26 (12%)** - magenta drape 2/2, color flip 1/1 exposed; everything else missed |
| End-to-end | 3/30 (10%) |
| Clean-recording FP | **3/4 episodes** flag hallucinated bugs |

Findings:
1. **The tier decomposition cleanly relocates the bottleneck**: coverage is largely solved
   by a 1.2B behavior-cloned explorer (83% exposure incl. every fall-through and teleport
   firing); identification from video is near zero (8%). Where coverage DOES fail (ghost
   drape never crossed), the E-tier reports it as unexposed instead of mislabeling it a
   perception miss - exactly the attribution the tiers exist for.
2. **Passive video audit hallucinates at scale**: ~100 claims over 34 recordings, 2 real.
   The dominant failure is EGOMOTION MISREADING - objects entering/leaving frame or
   getting occluded as the camera moves are reported as "suddenly appears/disappears/
   teleports" state bugs (e.g. 10 such claims in one no-collision-vase episode). The
   auditor has no ego-motion compensation.
3. **Evidence seen != defect diagnosed**: in the fall-through episodes the auditor
   described the fall ("sudden view cut to skybox", "sudden camera teleportation to sky",
   19 claims in one episode) yet never connected it to a floor-collision defect; judge
   correctly rejects. Embodied proprio made this same bug legible to 32B in Setting 1.
4. **Setting 1 vs Setting 2 detect nearly disjoint evidence**: S1 (agent audits itself,
   proprio available) finds blockage-family bugs (air wall, fall-through) + magenta;
   S2 (video-only audit) finds only what is legible in pixels alone (magenta). Decoupling
   fixes exploration coverage but strips the proprioceptive channel that carried most of
   S1's real detections; and S2's clean FP (75% of recordings) is catastrophically worse
   than S1's (~0-4%).

## Setting 3 (2026-08-30) — oracle-routed exposure (scripted bug-triggering tours)

Per project review: "give the explorer navigation that is guaranteed to trigger the bug and
see whether less video noise raises accuracy." The P2P VLA cannot follow navigation text
(3-arm ablation), so the route is executed by a scripted walker (`harness/scripted_tour.py`):
one deterministic per-case route that walks to the carrier, keeps it AND its siblings in
frame from mid-distance (2.6m), performs the triggering interaction (push the wall, cross
the hole, stare-turn-stare, go around to the aisle), 5-25s sim per episode. Same 32B VQA +
judge pipeline. Exposure = 100% by construction; recordings are 3-10x shorter than
Setting 2's.

### Three-setting comparison (auditor: Qwen3-VL-32B everywhere)

| setting | exploration | exposure E | found given E | end-to-end | clean FP |
|---|---|---|---|---|---|
| S1 embodied agent (32B, acts+audits) | agent's own patrol | n/a (self-directed) | n/a | **5/45 (11%)** | 0/6 |
| S2 VLA explore -> video VQA | P2P-1.2B, bug-blind | 26/30 (87%) | 3/26 (12%) | 3/30 (10%) | **3/4** |
| S3 oracle tour -> video VQA | scripted, guaranteed | **15/15 (100%)** | **3/15 (20%)** | 3/15 (20%) | **0/4** |

Findings:
1. **The de-noising hypothesis holds on the FP axis dramatically**: clean-recording false
   positives collapse from 3/4 episodes to 0/4 - short, purposeful footage removes the
   egomotion hallucinations almost entirely.
2. **Identification improves but stays low**: 12% -> 20% given exposure. S3 uniquely catches
   the self-drifting pot (an 8s stable dwell makes the motion legible - S2's wandering
   camera never did); the color flip is caught in both; magenta in all three settings.
3. **The audit-channel ceiling is the story**: with exposure guaranteed, framing optimal and
   noise zero, 12/15 bugs remain invisible to the strongest local video auditor - every
   static anomaly (floating/sunken/oversized/duplicated pot, portcullis: the auditor
   behaves as a CHANGE detector and never flags states), every proprio-dependent bug
   (air wall = walking-in-place on video, fall-through = "camera cuts to sky" x12,
   described but never diagnosed), and both hard viewpoint/state cases (backcull drape,
   despawn - the latter was caught once under a close-framing route variant, i.e. borderline
   sensitivity, not zero).
4. Setting-1's five finds (air wall, fall-through-as-reset, magenta x3) and Setting-3's
   three finds overlap only on magenta: embodied proprio and passive video observe largely
   DISJOINT evidence.

## S1 difficulty ladder (2026-09-02, launched) — priors added cumulatively, hard -> easy

Question: how much of Setting 1's failure is *task hardness* (open-world search with no
priors) vs *capability floor* (cannot recognize the defect even when pointed at it)?
Three constraints are stacked on the L0 baseline (= canonical S1, no priors):

- **L1 existence prior** — instruction states exactly ONE bug is present (definitely).
  The "if normal, finish without flagging" branch is removed. No clean arm: the prompt
  asserts a bug, so it cannot honestly run on sp00 (L0 already measures clean FP).
- **L2 type prior** — L1 + the bug's taxonomy category and two textbook examples of it.
  Example pairs are fixed per category, so for 9 cases one example coincides with the
  planted instance (exact-example: sp01 sp02 sp05 sp06 sp09 sp10 sp12 sp13 sp15) while
  6 get type-only info (sp03 sp04 sp07 sp08 sp11 sp14) - reported as a sub-split.
- **L3 space prior** — L2 + `spXX-*-near` configs: spawn ~3m from the bug facing it,
  instruction pins it within an inspection-zone radius (6 m; 8 m for the LOD case; 12 m
  for the leave-and-return streaming cases so their exitR=9 triggers stay reachable),
  runner emits a soft out-of-zone proprio note (no physical fence - that would collide
  with the airwall bug type). Spawn/facing/zone geometry verified by harness/near_verify
  (15/15: spawn err 0.00m, facing err <0.5 deg, bug inside zone; sp14 probe confirms the
  drape starts at the 8x8 mip from the 6.63m spawn and pops to 1024 on approach).

Grid: 3 levels x 4 Qwen models x 15 cases x 3 episodes (540 eps, no clean arm), scored by
the frozen judge protocol per level (`reports/sp-suite/s1-ladder-l{1,2,3}.md`).
Smoke check: 4B - which scored 0/45 at L0 - flagged the magenta drape on step 2 at L3,
so the ladder's dynamic range is real. Batch: scripts/run_s1_ladder.sh (overnight).

**Results (post-adjudication; full analysis `reports/sp-suite/s1-ladder.md`):**
found/45 by L0->L1->L2->L3: 4B 0->2->2->3; 8B 2->4->6->6; 30B 1->1->6->3 (non-monotone);
32B 5->5->6->6. The ladder NEVER unlocks a new bug class: the valid-find union is
{invisible wall, fall-through, magenta} at every level - priors saturate the two
already-findable channels (sp05/sp09 go 3/3 for models >=8B at L2/L3) and nothing else.
12/15 case types stay at zero even spawned 3m from the defect facing it with its category
and examples named. Type-only L2 cases (sp03/04/07/08/11/14): zero everywhere. The judge
initially credited 15 extra episode-finds at L2/L3; human audit rejected all 15 as
prior-echo hallucinations (braziers/ivy flagged as "floating objects", a red banner as
"missing texture" while the LOD drape is green and sharp at flag time, "reappearing
planters" whose triggers never fired - verified against event logs/trajectories/frames).
~30% score inflation at L2 caught only by the audit-every-positive protocol.

## S1 observation protocol v2 - film mode (2026-09-02, rerun launched)

User critique (accepted): single-frame observation structurally hides dynamics - a
post-action frame cannot show a collision happening, and `wait` is wasted (one frame
after waiting, nothing of what happened during it). Switch S1 to the film observation:
per action a low-res strip sampled at fixed SIM-time intervals + the full-res final view
(the world still pauses during deliberation; strips span only action windows).

Frame rate grounded in literature, not chosen ad hoc (see RELATED-WORK "Video frame-rate
grounding"): 2 FPS sim-time (dt=0.5s, max 8 frames/action, 480x300 + 960x600 final) -
matches Qwen-VL's native ~2 FPS video training, sits inside the 1-5 FPS envelope of
VideoGameQA-Bench (1 FPS) / TempGlitch (1 vs 5 FPS, denser ~= no gain) / bug-frame
retrieval (4 FPS). Long actions stretch the 8 frames across the whole window, so wait
becomes a genuine temporal probe.

Verified before launch: strips are sim-time spaced (settle-fall covered); the trembling
pot (sp08) is measurably visible across strip frames (~250 px localized diff at the pot,
zero elsewhere after the spawn-settle frame); pushing into the invisible wall films a
frozen view while proprio reports effort (film mode disables the stall early-return).
Note: probing mesh positions must convert through the gltf parent transform - local
offsets of +-10 "units" are +-8cm world (parent scale), NOT a broken tremble; visual
verification settled it.

Rerun: L0 (45 bug + 6 clean) + full L1/L2/L3 ladder x 4 models under film
(scripts/run_s1_film.sh; tags sp-film-* and sp-l{1,2,3}f-*), judged per level into
judge-matrix-film.md and s1-ladder-l{1,2,3}-film.md. Single-frame results are retained
as the observation ablation.

**Results (post-adjudication; full analysis `reports/sp-suite/s1-film-vs-single.md`):**
totals barely move (e.g. L3: 3/6/3/6 -> 4/7/8/4), but case-type coverage DOUBLES:
film's valid-find union is {sp01 float, sp05 wall, sp06 fall, sp07 ghost drape,
sp09 magenta, sp14 LOD pop, sp15 origin pile} = 7/15 vs single's 3/15. Firsts: sp07
found for the first time in ANY setting (30B walked through the drape plane, z
0.30->1.80 at x=2.44, "passage through a solid-looking object"); sp14 identified live
in its 8x8 state at 6-7m (8B/30B, "green banner pixelated/blocky"); sp15 real-asset
pile found in S1 by 4B standing on it; sp06 goes from 32B-only proprio inference to
3 models with verbally exact "falling through floor" claims (the strip films the fall).
Cost: film imports the egomotion false-alarm mode into S1 - L0 clean FP 30B 0/6->4/6,
32B 0/6->5/6 (4B/8B stay 0/6); 32B's L0 found drops 5->2 the same way. sp08 tremble
stays 0 everywhere despite measurably visible strip motion - film helps event-scale
evidence, not subtle-motion anomalies. Judge over-credited 16 episode-finds
(font/braziers as floating basins, untriggered sp12/13 claims, example-text echoes);
all killed by frame/event audit (21 new adjudications; drape-67 color corrected to
green after texture sampling - the earlier "blue" ID was a 69-occlusion misread).
Never found by anything, still: sp02/03/04/08/10/11/12/13 (8/15).

## Scoring protocol (frozen 2026-08-30)

1. Automatic pass: LLM judge (30B, temp 0) with reasoned verdicts (one-sentence rationale
   before match; v3 prompt), strict same-defect-type + same-object rule, per-claim.
2. Mechanical gates: event-timed cases require the claim's cited time inside the logged
   event window; sp10 requires it inside the seen-from-behind window (pose-derived).
3. Joint fallback: if no single claim matches, the episode's deduplicated claim set is
   judged once as a whole (complementary partial observations), keyed per episode.
4. **Manual adjudication of every positive**: each judge-MATCHED claim (single or joint) is
   human-audited against frames/trajectories; overrides with written reasons live in
   `eval/adjudications.json` (6 entries: 5 false credits removed - brazier-as-basin,
   banner-blocking misattribution, sky-cut non-diagnosis x2, egomotion drape flicker -
   and 1 vocabulary-rescued true positive). Negatives are spot-checked, not exhaustively
   audited: reported "found" counts are lower bounds with verified numerators.

## Incident / correction log (methodology provenance)

- Ladder judge all-zero artifact (2026-09-02): the first s1-ladder matrices reported 0/45
  for every model at every level. Cause: judge_sem's candidate collector kept only
  variant == "bug" episodes, so the ladder's l1/l2/l3 flags were never sent to the judge
  ("0 deduplicated candidate notes") and defaulted to no-match. The scoring loop counted
  the episodes (correctly) but the verdict lookup found nothing. Filter fixed to skip only
  variant == "clean"; all three levels re-judged. Historical results unaffected (previous
  task names only used bug/clean variants). Lesson: an all-zero matrix over 371 flags is a
  pipeline smell, not a result - cross-check the "candidates to judge" count.
- tc02/03 originally lever-gated; levers proved inoperable (0/40) → redesigned to
  direct-interact doors; one rerun invalidated by an instruction/config mismatch (archived at
  `runs/archive-mismatch-tc0203`); final numbers use door version with matched instructions.
- Torch flag radius: instruction says observe from a distance; scoring radius raised to 6 m
  (per-answer radius support) after valid remote detections were rejected at 3 m.
- tc09 crate initially placed in the walking lane → collision-bump false "detections";
  semantic layer filters these; future layouts keep L1 objects off-lane.
- env1 ring layout fixed after pilot (cyan ring was occluded on fountain platform).
- InternVL3_5-38B: two orchestration failures (self-matching pkill), one context-length
  failure (>14588), then multi-image prompts infeasible (>7 min/request) → single-frame subset.
- LLM-judge validation (Qwen3-VL-30B judge, temp 0, 331 judgments): 94% agreement with the
  regex semantic layer; all model rankings unchanged; one borderline cell flipped (4B tc10).
- Totals-table correction (2026-08-28): an earlier published totals row for 30B-A3B (23/6/18)
  had absorbed the invalidated instruction-mismatch rerun of tc02/03; the corrected door-version
  rerun leaves those cells flagless for 30B, giving the true totals 17/6/9 (32B 34->33, FP 25->22).
  Per-case tables, family rollups and P/R tables were computed from clean data and were unaffected.
- Localization geometry (2026-08-28): position matching extended with per-answer
  extent/global geometry after the drifting-crate/tint critique.
- Metric simplification (2026-08-29, project decision): position matching retired from scoring
  entirely - it is undefined for moving/global bugs, and as an eligibility gate it suppressed
  genuinely correct remote reports (dropping it raised 8B's instant-open-door detections from
  0/5 to 3/5 and 4B's half-stuck-door from 0/5 to 2/5, both described correctly from ~6m).
  The canonical metric is judge-based "found" (eval/judge_sem.py); localization is an
  auxiliary diagnostic only. Rankings are unchanged; 32B remains the only model detecting the
  full temporal family.
- sp07 redesign (2026-08-30, found in the user's manual review): v1's "no-collision vase"
  targeted mesh_0, which is actually a chain-hung brazier mounted on a solid ivy column -
  the walk-through phenomenon was physically untestable (the column blocks regardless), and
  the manual-check beacon exposed the mislabeled carrier. A v2 attempt (ghost floor planter)
  also failed verification: knee-high pots are stepped over by the player capsule in the
  clean world too. Final v3: ghost DRAPE (one of 10 drapes passable, the other 9 solid -
  sibling-consistency anchored, walk-through verified bug-vs-clean: z=3.00 vs z=1.23).
  All sp07 v1 results in both settings voided (archived runs/archive-sp07-ghostvase/),
  cell rerun with v3. sp_verify now demands a physical walk-through contrast, not just
  collider-list absence. Also fixed: human.html beacon latch (a V-press before the async
  answers fetch resolved permanently suppressed the bug beacons).
- sp10 redesign (2026-08-30, user suggestion): v1 culled the hall-facing side, leaving an
  "empty slot + invisible blockage" that is epistemically confusable with an air wall from
  the walkway (a brief grading amendment accepting slot-bound invisible-barrier reports was
  superseded the same day). v2 culls the BACK side instead: the hall view is pixel-identical
  to clean (verified meandiff 0.5), the drape collides normally, and the defect manifests
  ONLY when viewed from the aisle behind (verified: target invisible, neighbors visible,
  aisle reachable on foot via the east end). Ambiguity eliminated; the case is now the
  suite's hardest pure-viewpoint bug, discoverable only by going around. v1 results voided
  in both settings (runs/archive-sp10-hallcull/), cell rerun with v2.
- watchUnseen origin-trigger fix (2026-08-30, caught by the Setting-3 oracle tour): the
  look-away watcher for despawn/teleport used getWorldPosition() of the target mesh, but
  Sponza gltf child meshes bake vertices in world space with node origins at (0,0,0) - the
  watcher was tracking the SCENE ORIGIN, not the pot. Random exploration masked it (origin-
  relative gaze happened to cross thresholds mid-walk, so events did fire and the despawn/
  teleport phenomena genuinely occurred in past episodes - at semantically arbitrary times);
  the deterministic stare-turn-stare tour route fired ZERO events and exposed it. Fixed to
  per-tick world-AABB centers; sp_verify extended with trigger-timing assertions (no
  premature fire while staring, exactly one event at the look-away). sp12/sp13 cells rerun
  in Settings 1+2 under exact semantics (old data: runs/archive-sp1213-origin-trigger/).
- Realism revision (2026-09-01, user critique "some bugs are artificial" + literature
  grounding): six cases redesigned so every bug has a real engine causal story, aligned
  with World of Bugs' injected-bug catalog and the project taxonomy's edit-location column
  (full mapping: reports/sp-suite/BUG-PROVENANCE.md). sp04 side-by-side duplicate ->
  co-located double-spawn (7cm offset, doubled rim/foliage; the old version read as
  plausible clutter); sp08 metronome drift -> in-place physics-jitter trembling;
  sp12/sp13 gaze triggers -> distance-based streaming semantics (visit <5m then leave >9m;
  turning around alone no longer triggers - verified); sp14 metronome color flip ->
  texture-LOD pop at a 6m threshold (8x8 mip vs 1024 sharp, distance-driven); sp15 lone
  portcullis -> interpenetrating prop pile at the world origin (failed-spawn classic).
  sp_verify extended to 61/61 (incl. co-location, tremble-span, leave-trigger timing,
  map-resolution pop, pile-overlap assertions). All six cells rerun in all three settings;
  old data archived (runs/archive-realism-v1/).
- sp15 v3 (2026-09-01, user review): v2's pile used fabricated factory assets (untextured
  crates + torch) - violating the suite's own real-assets-only principle. Replaced with
  mesh_pile: CLONES of Sponza's own planters and hanging brazier dumped interpenetrating at
  the world origin (originals verified untouched). sp_verify 62/62; v2 data archived
  (runs/archive-sp15-crates/), cell rerun in all settings.
- Setting-2 false credit + event-time gate (2026-08-30): a VQA claim about a pot
  "appearing and disappearing at t=24-26s" was judge-matched to the despawn case whose
  event actually fired at t=2.1s - an egomotion hallucination with coincidental phrasing.
  Event-timed cases (fall-through/despawn/teleport/colorflip) now additionally require the
  claim's cited time to fall inside the logged event window [event-3s, event+8s]
  (eval/vqa_audit.py); sp12 corrected 1/2 -> 0/2, totals 3/30 -> 2/30.
- Suite v2 (2026-08-29, project decision): TC corridor suite superseded by the SP
  Sponza-native suite. Grounds: (a) several TC bugs were not unambiguously bugs
  (auto-closing and instant-opening doors are defensible design; tc02's "no animation" still
  showed a visible opening transition); (b) toy corridors are not paper-grade environments;
  (c) the world previously kept running while the VLM deliberated - now turn-based
  (sim time flows only during actions). TC results remain above as historical baselines.

## HS suite - Family House (second real environment, 2026-09-06)

Environment: `env/house/house.js`, the two-storey family house built for the candidate
environment review (real-scale CC0 Poly Haven furniture, PBR textures, 12 rooms on two floors,
stairs; ~1M triangles baked into the BVH). Bugs `hs01`-`hs15` mirror `sp01`-`sp15` type-for-type
on the house's own repeated elements (4 identical dining chairs, 3 bar stools, 2 armchairs,
2 nightstands ...): float / clip / scale / double-spawn / air wall (hall) / floor hole (hall) /
ghost kitchen island / trembling floor lamp / magenta TV cabinet / sofa culled from behind /
x-ray coffee table / plant unloaded on leave / dining chair state reset / rug LOD pop /
furniture pile in the hall. `hs00-clean` shared. Uniform neutral patrol instruction covering both
floors (35 steps). Player radius 0.22 (0.32 in Sponza): the 0.32 capsule cannot pass 0.5-0.6 m
furniture gaps, which would read as fake invisible walls.

Verification: `harness/hs_verify.py` (behavioral assertions per case, screenshots in
`runs/hs-verify/`). Settings run by `scripts/run_house_night.sh`: S3 oracle tours
(`runs/hs-tour-v1`), S1 film L0 (`runs/hs-film-<model>`), S2 P2P explorer (`runs/hs-vla-p2p`),
VQA audits and the S1 judge -> `reports/house-suite/`.

Verification (2026-09-06): `harness/hs_verify.py` 58/58 assertions pass (clean house fully
patrollable on both floors incl. the stairs; every bug manifests as specified; screenshots in
`runs/hs-verify/`). Two harness-side defects found and fixed on the way: three-mesh-bvh's bake
silently dropped invisible meshes and corrupted KHR_mesh_quantization positions into phantom
triangles (see candidate_environments/src/house/README.md).

Known suite issue (found in the night run, to fix in v2 of the suite): hs10 culls only the sofa,
so its throw pillows (a separate object) stay visible and "float" when the sofa disappears - the
32B auditor reports the pillows, not the missing sofa. Next iteration: cull `PILLOW#1` together
with `SOFA#1`. Also note that a bright magenta cabinet (hs09) is not reported as a defect by
30B/32B in the VQA channel - it reads as deliberate colour in a furnished interior.

### Results (night of 2026-09-06; judge Qwen3-VL-30B temp 0, cache runs/judge_cache_hs.json)

S1 embodied self-audit, film observation, 15 bugs x 3 + clean x 6, 35-step budget
(`reports/house-suite/s1-judge.md`):

| model | found | clean FP eps | P | R | F1 | flags |
|---|---|---|---|---|---|---|
| Qwen3-VL-4B | 2/45 | 4/6 | 0.00 | 0.04 | 0.01 | 742 |
| Qwen3-VL-8B | 4/45 | 2/6 | 0.02 | 0.09 | 0.03 | 242 |
| Qwen3-VL-30B-A3B | 3/45 | 4/6 | 0.01 | 0.07 | 0.02 | 309 |
| Qwen3-VL-32B | 3/45 | 6/6 | 0.02 | 0.07 | 0.03 | 169 |

Per case: only hs05 (invisible wall in the hall) is found by every model (30B 3/3, 32B 2/3,
8B 2/3, 4B 1/3); singles for hs09 magenta cabinet (4B, 8B), hs10 sofa culled from behind (8B),
hs11 x-ray table (32B). Twelve of fifteen types are never found by any model - the same
"collision channel saturates, static visual anomalies stay blind" picture as Sponza (SP L0 film:
32B 5/45). Clean FP is worse than in Sponza (4-6 of 6 episodes for 30B/32B): agents that end up
facing a plain white wall report "the scene is blank/not rendered" and flag it repeatedly
(30B: 20 flags in one episode); 742 flags for 4B is a flag storm.

S3 oracle tours + VQA (`tour-vqa-30b.md`, `tour-vqa-32b.md`): exposure 15/15 by construction;
I|E 0/15 with the 30B auditor, 1/15 with the 32B auditor (hs06 fall-through floor, reported as
the sudden sky view; claims 17, clean FP 2/4). The auditors see but mislabel: the magenta cabinet becomes "abnormal scale", the fall
through the floor becomes "sudden sky environment with a floating green platform", and the
culled sofa is reported through its now-floating pillows (see the suite note above).

S2 P2P blind explorer x2 seeds, 60 s sim (`vla-vqa-30b.md`): exposure 15/30 - the explorer
mostly paces the entrance hall (first episode: 9 m of path inside x -0.1..0.8), so only bugs
on or next to the hall get exposed; I|E 2/15 (hs01 floating chair 1/2, hs05 air wall 1/1), clean FP
1/2, 115 claims.

Run log: `runs/house-night.log`; summary `reports/house-suite/summary.md`.

**Step budget (2026-09-06, after the night run):** 35 steps was far too short for a 12-room,
two-floor patrol: every model hit the cap in >=45/51 episodes, visited a median of 1-3 of 13
rooms (30B never went upstairs, path median 6-23 m), and `done` was used in only 0-6/51 episodes.
Most zero-detection cases are therefore coverage failures, not recognition failures. The HS budget
is raised to 90 steps (harness/tasks.py); the 35-step runs above stay as the first pass.
Film-rate ablation at 90 steps (f2 = 2 fps x 8, f4 = 4 fps x 16, f8 = 8 fps x 32, ~4 s window),
30B + 32B: `scripts/run_house_fps90.sh` -> `reports/house-suite/fps-ablation-90.md`.
The aborted 35-step f4 run of the 30B is kept in `runs/hs-film4-qwen30b`.

**Wall texture (2026-09-06, after the first 90-step episodes):** a larger budget did not raise
coverage - 4 of the first 7 30B episodes were "white-wall storms": the agent ends up pressed
against a flat cream wall, the film frames are a uniform fill, and it reports "blank white void /
rendering failure" 40-70 times without turning (`runs/hs90-f2-qwen30b`). Sponza's stone walls
keep texture at close range; the house's paint was colour + normal map only. The wall paint (and
the stair sides) now carry a normalised plaster grain (beige_wall_001 diffuse divided by its mean,
so the paint colour is unchanged and only a +-10 % grain remains). All results above were
produced with the flat walls; the 90-step film-rate ablation is rerun on the textured walls.
(The first 90-step 32B attempt also lost its vLLM server on GPUs 2+3 and recorded nothing.)

**Film-rate result, 32B (2026-09-07 04:30 UTC, textured walls, 90 steps):** f2 3/45 found (hs05 3/3),
f8 2/45 (hs05 2/3); clean FP 6/6 in both; flags 366 vs 383 (clean-episode flags 38 -> 56); 49/51
episodes hit the step cap in both. A 4x film rate buys nothing at ~2.6x vision tokens, so f2 stays the
canonical S1 setting and f4 is not run. The clean-house false flags are mostly environment presentation
(low-poly garden seen through windows, static doors, real walls reported as "invisible walls"), see
`reports/house-suite/fps-ablation-90-notes.md`. 30B f2/f8 follow (`fps-ablation-90.md`).


## HS suite, f2 film, 90 steps — all S1 settings (2026-09-07, complete matrix)

Full tables: `reports/house-suite/summary-f2-all.md` (generated by `scripts/house_f2_summary.py` from
`s1-f2-l0.md`, `s1-ladder-l{1,2,3}.md`, `fps90-*.md`).  Runs: `hs90-f2-<model>` (L0), `hs-l{1,2,3}-<model>`.

**L0 (no priors), 15 cases x 3 + 6 clean:** found 4B 1/45, 8B 3/45, 30B 3/45, 32B 3/45; clean FP 8B/30B/32B
6/6 (4B 2/6); flags 4B 1589, 8B 529, 30B 880, 32B 366 -> P <= 0.01 everywhere.  Only hs05 (invisible wall) is
found by every model; 8B once hits hs09 (missing texture).  All models run to the 90-step cap (39-45/45).

**Ladder (existence -> type -> near spawn):** 32B 3 -> 3 -> 5 -> 6 / 45, 30B 3 -> 0 -> 3 -> 5, 8B 3 -> 4 -> 4 -> 7,
4B 1 -> 1 -> 1 -> 0 (its ladder needed a redo: the vLLM multimodal processor cache asserted mid-run, fixed with --mm-processor-cache-gb 0).  Union of found types over the whole ladder: {invisible wall, fall-through floor,
missing texture, plant unload}; 11 of 15 types are never found at any level by any model.  Precision rises
only to 0.03-0.10 at L2/L3.  With an existence prior the episodes collapse to ~20 median steps: the agent
flags something and stops (40-45/45 episodes carry a flag, ~95 % of them wrong) — the same prior-echo
behaviour seen on Sponza.

**Conclusions.** (1) The house is recognition-limited, not budget-limited: 90 steps and near-spawn priors
do not unlock the visual bug types; collision-type bugs (air wall, hole) are the only ones found reliably,
because the agent *feels* them.  (2) Model size (4B -> 32B) changes the false-flag volume, not recall.
(3) Frame rate is irrelevant (f2 = f8).  (4) Clean-episode false flags are environment presentation:
the low-poly garden seen through windows, static doors, real walls reported as invisible walls, and one real
artefact (a floating row of wine bottles, fixed in the source; the harness module is regenerated after these
runs).  Next: make the SP suite comparable (it still runs 25 steps), and reduce presentation confounds
before the next suite version.

## WT suite — reef dive (candidate 10, standalone page) — 2026-09-07

Third environment family after SP (Sponza) and HS (house).  The reef is the polished
`candidate_environments/10_beautiful_water_clean_constrained.html` (three r185, WebGL pipeline, first-person
diver).  Unlike HS it is **not** ported into env/core.js: the page implements the harness page contract itself
(`window.__env` in `src/water/app/harness.js`; the bridge opens any config whose JSON names a `page`), so
harness/runner.py, the film observation and eval/judge_sem.py run unchanged.  Bug injection is in the page
(`src/water/app/bugs.js`, `?bug=wtXX-slug`), 17 cases: wt01-wt15 mirror the SP/HS taxonomy type by type
(floating boulder, sunken rock, oversized coral, double-spawned rock, invisible wall, seabed hole, no-collision
rock, trembling coral, magenta rock, rock invisible from behind, x-ray coral, coral cluster unloads, rock
position resets, coral LOD pop, coral pile) plus two reef-specific behaviour bugs suggested by the reviewer:
wt16 fish swim backwards (tail-first) and wt17 fish swim upside down.  Answers are dumped from the page
(`tools/gen_water_cases.py`), verification `tools/wt_verify.py` (12/12), catalogue
`reports/water-suite/catalog.jpg`.

Environment fixes that came out of the review: rocks are now solid for the diver (ellipsoid colliders — the
clean reef previously let the diver swim through every rock), the barramundi swam tail-first in the clean
scene (head is at +z in the glTF; the extra flip was removed), the page starts in first person.

Limits of this first integration: the S1 action set is horizontal (forward/back/turn/look) — the diver
cannot dive/surface, so the spawn is at -4.4 m near reef height; the world runs in real time between
actions (fish keep moving), unlike the sim-clock pause of core.js.

Pilot: `scripts/run_water_pilot.sh` — 30B, f2 film, 90 steps, 17 bug episodes + 2 clean ->
`reports/water-suite/s1-pilot-30b.md` (results appended below when judged).

**Pilot result (30B, 2026-09-07 08:34 UTC, 17 bug episodes x 1 + 2 clean, f2, 90 steps):** found 1/17
(wt03 oversized coral), clean FP 2/2, 45 flags in 19 episodes (P 0.02, R 0.06).  15/19 episodes ran to the
90-step cap; flags/episode 2.4.  What the false flags describe: the mooring buoy ("artificial pole with disc
top"), sea fans / staghorn corals ("floating coral not attached", "skeletal hand protruding from rock",
"pink arm-like object"), the caustics ("hexagonal pattern with glowing lines on the sand"), and one
"split-screen rendering artifact".  Same picture as SP/HS: near-zero recall, and the environment's own
stylised elements are read as defects — the reef's procedural corals and caustic pattern are the first things
to make more photoreal before a full WT run (3 episodes x 17 cases x 4 models).

## AF / WL / CT suites (2026-09-08): bug catalogues for the airfield, wilderness and cottage

All three candidate environments now carry a 17-case catalogue built the same way as the reef (WT): 15 cases mirror
the SP/HS taxonomy (float, clip, scale, double-spawn, air wall, hole, ghost collider, jitter, magenta texture,
back-face cull, x-ray, unload, state reset, LOD pop, spawn pile) plus two environment-specific cases
(airfield: mis-rotated barrier, barrel without shadow; wilderness: terrain tile seam, floating grass; cottage:
windows without glass, time-of-day jumps).  Each page implements the harness contract through
`candidate_environments/src/common/harness_page.js`, so `harness/runner.py` runs S1 audits on them unchanged
(`audit_{af,wl,ct}XX_bug`, `audit_{af,wl,ct}00_clean`, 90 steps).  Bridge smoke on every suite: walk / turn / look /
film / flag work; the air wall blocks, the ghost object lets the walker through, the hole drops and respawns.
Catalogue sheets: `reports/{airfield,wilderness,cottage}-suite/catalog/catalog.jpg`.  Judge ground truth and labels
are in `eval/judge_sem.py`; configs and answers in `env/configs/{af,wl,ct}*.json`.
S1 pilot (Qwen3-VL-30B, f2, 90 steps, 17 bugs x 1 + 2 clean per suite): airfield 0/17 found (clean FP 1/2, 121 flags),
wilderness 2/17 (1/2, 75 flags), cottage 2/17 (2/2, 591 flags) - details and the coverage analysis in `reports/new-suites-0908.md`.

## Bug review and collision fidelity (2026-09-09)

Every environment is now reviewed the same way: a single HTML file, `?bug=<id>` injects a case, and a review overlay
(`candidate_environments/src/common/bug_picker.js`) lists the cases, describes the defect and jumps next to it;
`bugs.html` in the release bundle links every case.  The house and Sponza files are the harness scene itself packed with
their assets (`tools/pack_harness_page.py`), so the review pages have the same mesh-level (BVH) collision the agent
runs with; the old box-collider house walkthrough is retired.  Airfield props got cylinder bodies where the shape is
round (barrels, tanks, hydrant, jerrycans) and a slim pole body for street lamps (their bounding box blocked the whole
area under the arm).

## Three.js suites: second human review round (2026-09-13/14) and revisions (2026-09-15)

Four reviewers rated the 105 three.js review tasks on the review website (211 reviews on `envs-2026-09-12`: 137 pass,
40 uncertain, 34 fail; export and per-case decisions in `reports/threejs-review-20260915.md`).  Reproducing the complaints
on the built pages found four defects on our side before any bug was judged: the wilderness page took the review site's
`&seed=5` as the *world* seed, so its position-authored catalogue (seed 7) was not present in the reviewed world (12 of 17
WL cases "not found"; the five seed-independent ones passed); the WL09 site rubric still named the old carrier; the cottage
day cycle silently restored the well's material ~10 s after loading (CT09 "reverts"); and CT16 left the door knobs floating
in the empty doorway.  Decisions: 34 tasks reworked (revision 2, mostly larger/clearer mutations, relocated or landmark
carriers, tilt+sink instead of sink-only, identical-copy piles, an x-ray car instead of a crate, lamp instead of barrel for
the missing shadow, a 1 s day/night flicker with the normal cycle stated in the scene text), one retired (WT06: a buoyant
diver "sinking through sand" has no natural collision reading), rubrics clarified for HS10 / AF10 / SP07 / CT13, everything
with >= 2 passes untouched.  Split votes were checked against the page: CT07's "clean tree is passable too" does not
reproduce (clean blocks at 1.8 m, ghost passes 3.7 m), WT05's wall blocks 3 m in front of the spawn, HS10 culls as designed.
Release `envs-2026-09-15` (`candidate_environments/BUILDS.md`); review-site manifest updated with version aliases for the
unchanged tasks so their acceptance carries over.

**Round 3 (2026-09-16).** The owner re-reviewed the 35 revised tasks (43 reviews: 34 pass, 10 fail/uncertain with comments).
Fixed as asked: sp02 (pot now lies 65 degrees, half in / half out of the floor), af15 (heap solid), wt03 (giant fish keeps
its distance from the school), wt13 (armed from the start lane, side switch after a swim north and back), wl12 (the start
boulder unloads), wl13 (the tall pine jumps 10 m).  Retired as not fixable cleanly: sp03, wt04, wt10, wl04, ct16.
Release `envs-2026-09-16`; 252 review-site entries (99 three.js).

**Round 4 (2026-09-16, later).** After the owner's re-review of the round-3 fixes, wt03, wt13 and wl13 were retired as well (giant fish still clipping other schools; relocated boulder floating; pine jump too hard to notice). Release `envs-2026-09-16b`; 96 three.js review entries.

**Clean review view (2026-09-16c).** Checked that the agent's observation is the bare canvas: `harness/bridge.py` only calls
`window.__env.act`, whose frames come from `canvas.toDataURL` (`env/core.js`, `src/common/harness_page.js`); no DOM element
can enter a frame, the only compositing is the 1.5 s boundary notice, and `core.js` skips the aim highlight in agent mode.
The review site's pages (`?bug=…&noui=1`) did not match: an audit with the new `tools/review_clean_audit.py` found 8 visible
DOM elements over the Sponza/House canvas (the menu card with the case description and "Show bug answers"), 14 on the reef
(observer panel, key hints, badge, DOM vignette), 19 on the cottage (day-cycle buttons, Credits, WASD hints, camera-distance
slider), the "Constrained area" badge on the wilderness, and keys the agent does not have (V beacons / third person, Space
jump, R atmosphere shift, Shift+R scenario restart, T HUD, ~ console) changed the world or the camera.  Every page now
embeds `src/common/noui_block.html` (via `src/common/noui.py` from all build scripts and the release relayer): under `noui`
all overlays are hidden and those keys are swallowed; the packed pages take the pointer on a click on the view.  After the
rebuild the audit shows 0 visible elements on all six pages and unchanged world state after the blocked keys.  Release
`envs-2026-09-16c`, coordinator release `threejs-envs-20260916-v3` (all 96 three.js entries keep their reviews through
version aliases; no revision bumps, no new "Updated" notes - the cases themselves are unchanged).  Correction the same
day: the site labels reviews by exact version tuple, so every rebuild since 2026-09-15 had moved the reviews of unchanged
tasks to "earlier build" (none current after the first 16c manifest); the manifest was republished with every task pinned
to its last content change (`pin_content_versions.py`, coordinator release `threejs-envs-20260916-v5`, served page hash in
`page_sha256`): 161 reviews shown as current, 10 earlier build, 58 older revisions.  Page-only rebuilds keep the content version.

## VLA arm (2026-09-17): Open-P2P 1.2B explores the held-out three.js cases, scored by heuristic exposure

Setting agreed with the owner: the largest Open-P2P model (1.2B, the Setting-2 explorer), bug-blind, instruction
"Explore this place. Walk around and look at everything.", budget 1200 ticks x 50 ms of *simulated* time (the four
standalone pages got a virtual clock, `?vclock=1` in `src/common/harness_page.js` / `src/water/app/harness.js`, so a tick
is exactly 50 ms on any device - the wall-clock mode under-drove the airfield walker to a third of its speed on this
machine), one episode per task, no VLM auditor or judge: exposure = geometry + events (`eval/vla_exposure.py`, bug
positions in `reports/eval-task-sets-2026-09-17.positions.json`), path length / visited cells as secondary numbers.
Held-out sets: 87 three.js + 126 Unreal tasks (`reports/eval-task-sets-2026-09-17.json`, ICL demonstration sources
excluded).  Drivers: `harness/vla_explore.py` (three.js), `harness/vla_ue.py` (Unreal through the paused AuditorRemote
step interface, tick -> turn/look/move steps), `harness/p2p_server.py` (`--precision`, host-RAM checkpoint load,
`harness/p2p_slim_ckpt.py` writes a 5 GB state_dict-only checkpoint), remote inference over ssh (`--p2p-host`).

Findings: (1) in a paused world the policy often enters an idle mode from the first ticks or after ~200 ticks (v1 run,
list A, 44 episodes: mean W-held 24%, three episodes fully idle; `reports/vla-threejs-v1-exposure.md`, 22/44 exposed);
a view-only nudge does not break it, resetting the model state does - v2 runs with `--idle-nudge 40` (look-around +
`p2p.reset()` after 40 idle ticks, counted in `meta.n_nudges`).  (2) torch.compile (~6 min per server start) gives
120 ms per act and 7.5 GB instead of 300 ms / 11 GB in eager mode with identical behaviour on real frames.
v2 result (87 episodes, 4 drivers: 2 local + 2 with the model on rain2's 3090 Ti, 2 h 20 min): exposed 52/87 - SP 9/13,
HS 10/15, WT 7/12, AF 11/18, WL 7/14, CT 8/15 (`reports/vla-threejs-v2-exposure.md`); mean W-held 41%, 92 m path,
4.5 resets per episode, no fully idle episode.  Exposure thresholds (view cone cos 0.75, per-suite distances, 0.5 s
dwell; approximations for backcull / xray / lodpop / unload) are a first pass, to be checked against the videos.

**Gemini video judge (2026-09-18, `eval/vla_video_judge.py`, `reports/vla-gemini-v2/`).** gemini-3.8-flash (thinking
medium) reads each recording as 120 timestamped frames with the SAME knowledge the iclr VLM agents get (task instruction,
public environment description, the one in-context example of the task's subcategory) and answers in the agents'
flag_bug structure; every report is graded against the planted bug's ground-truth text by the strict judge prompt
(gemini-3.8-flash, thinking low; automatic estimate, `grades-template.json` for the manual procedure of the VLM arm).
All 87 episodes, one pass, 11.7 M prompt tokens, 47 s per episode with 8 workers.  Result: found 23/87 (26%); 89 reports,
23 matched, 66 unmatched (precision 26%), 72 episodes carry at least one report.  By the pitch-aware exposure
heuristic: exposed 15/51 (29%) vs not-exposed 8/36 (22%) - but the eight "not exposed" hits are real detections
(magenta boulder, upside-down fish / tree, terrain hole, LOD pops, air wall, unloaded pine), i.e. the heuristic
under-counts exposure for anomalies visible from far away; the judge's own verdicts are the better exposure witness
for those kinds.  Typical false positives: barriers / crates read as floating or intersecting from oblique views, and
objects "disappearing" when the camera turns (ego-motion misreading, as in Setting 2).  The obvious oversized hydrant
(af03) was in view for 4 s and still reported as "squished barriers".

### VLA arm, Unreal batch (2026-09-18, running)

Environment version = the review site's current AWS release `unreal-area-3x-20260918` (published by ziyan on 2026-09-18; the local
review coordinator still serves the older builds without an exploration policy).  The release's Codex workspace on this machine,
`/home/ubuntu/unreal-auditor/unreal-area-3x-20260918/`, records the AWS live profiles (catalog entry + launch profile + exploration
policy per task); `tools/ue_aws_profiles.py` mirrors it onto local copies of the same builds (all 11 AWS binaries found here:
`exploration-v2-20260917/packages/*`, `subway-workspace/dist/concourse-cleanup-20260918-v2`, and the Indoor build recompiled that
day for `excluded_bounds`; sha256-verified) -> `reports/ue-aws-profiles-20260918.json` (143 entries: 17 clean baselines + 126 bug
tasks).  The 126 bug tasks are the held-out set of 2026-09-17 with S20 (retired on AWS) replaced by the new S22 (Concourse
waterfall wall, marked "candidate" in the catalog).  What the release changes for an explorer: every task launches with
`-AuditorExplorationTask=<id> -AuditorExplorationPolicy=<policy.json>` (`reports/ue-policies-20260918/`): the walkable region is
enlarged to 3x its exported area (Indoor: minus stairwell exclusions), and the pawn is teleported to a frozen "farther start"
(policy `spawn`/`yaw`: farther from the bug's focus point than the authored start, looking 110-150 deg away from it) - the same
start the VLM agents get.  The catalog's bug content did not change (only exploration metadata, six Concourse scene repairs and
16 rubric wordings).  Observation = the game's own frame (960x540 -> 192x192), which includes the minimap and crosshair, as on
the review site and for the VLM agents.

Driver: `harness/vla_ue.py --profiles ...` (task-keyed profiles; the launch keeps `-ExecCmds=t.MaxFPS 30` like the VLM harness
`scripts/native-agents/remote_unreal.py`; after reset it checks that the pawn stands on the policy spawn with the policy yaw and
that the game logged `AUDITOR_EXPLORATION_READY`, and aborts the episode otherwise), `--claim` for several drivers over one list.
Smoke run (`runs/vla-ue-smoke-aws`, H01/A01/MV01, 100 ticks, 600M model): start checks exact (0 cm, 0.0 deg); an Unreal instance
takes 2.5-3 GB of GPU memory; 0.46 s per tick with the eager 600M (~0.16 s of it Unreal).  Batch `runs/vla-ue-v1`
(`scripts/vla_ue_driver.sh`): 1200 ticks x 50 ms, idle-nudge 40, one episode per task, three drivers - r1/r2 with the 1.2B
model compiled on rain2 (7.3 GB each), l1 with a local compiled server; three Unreal instances on the local A10.

Exposure heuristic for Unreal: `eval/vla_exposure_ue.py` (target = the policy's focus point = tagged target actor / authored aim;
same cone rule as the three.js scorer, family distance limits 7-16 m; per subcategory: G/S/V3/V4 in view >= 0.5 s, C1 walked
within 1.2 m, C2 held W without moving within 2.5 m, C3 contact then in view, T1/T2 seen - away (>= 8/12 m or out of view
>= 1 s) - seen again, T3 that or >= 2 s in view, V1 two directions >= 90 deg apart or centred view, V2 near (< 6 m) and far
(> 10 m) views; H15 needs a door interaction the VLA cannot issue).  No occlusion test.
Batch notes: the 15 Urban tasks are excluded - their builds (per-task maps, no `?Task=`) carry the exploration plugin but not the
AuditorRemote IPC interface (the game reaches AUDITOR_EXPLORATION_READY and never answers `-AuditorServe` commands; U011 timed
out), the same builds the VLM batch holds with `--hold-task`.  Effective task set 111 (126 minus Urban).  Throughput: three
960x540 instances saturate the A10 (a paused game keeps rendering at its `t.MaxFPS` cap), 0.6-0.85 s per tick, 12-13 min per
episode; the batch therefore runs the games with `t.MaxFPS 20` (fixed time step: identical frames per step and observation,
only the wall clock changes), 640x360 was rejected because the minimap is fixed in pixels and would cover much more of the view.
Throughput fix (23:15): `t.MaxFPS` is ineffective under the plugin's fixed time step, so a paused game renders in a tight loop
and three instances keep the A10 at 100% (R01 took 844 s even with the cap).  The driver now SIGSTOPs the game process while
the policy thinks and SIGCONTs it for the tick's steps (`VLA_UE_FREEZE=1`, default): no simulation or observation change (the
world is paused between commands anyway), only the idle rendering disappears.  Verified on H01 (20 frozen ticks, results ok,
frozen process uses no CPU); drivers replaced one by one at episode boundaries (episodes H01, S01, A01, I02, R01 ran without it).

**Unreal batch result (2026-09-19 morning, `runs/vla-ue-v1`, 111 episodes = 126 AWS bug tasks minus the 15 Urban ones).**
All 111 start checks exact (policy spawn + yaw, AUDITOR_EXPLORATION_READY); median 714 s wall per episode (rural 577 s ...
ancient 899 s), 23.3 driver-hours on three drivers; 0.4 idle nudges per episode, no stuck recoveries.  The explorer walks
25 m per 60 s episode (median), holds W 21% of the ticks, and stays far from the planted object: the frozen farther start is
13.6 m from the focus point (median) and the closest approach is 12.0 m (median); only 22 episodes came within 6 m, 7 within 3 m.
Heuristic exposure (`reports/vla-ue-v1-exposure.md`): 17/111 (rural 6/16, ancient 5/23, industrial 3/19, medieval 2/22,
indoor 1/14, subway 0/17; all collision kinds and V2 0).
Gemini video judge (`reports/vla-ue-gemini-v1/`, same protocol as the three.js run, 15.0 M prompt tokens): found 11/111
(10%); 74 reports, 11 matched (precision 15%); 70 episodes carry at least one report.  Exposed 4/17 found (A05 bench
proportions, I13 floating chair, MV07 popping chair, R13 floating rock) vs not-exposed 7/94.  Three of the seven are the
C2 invisible-wall tasks (I05, H05, S07): the poses show no sustained blocked movement at all (no run of >= 0.5 s with W
held and no displacement), so those "unexpected collision" reports are primed by the C2 demonstration and matched by the
text judge without evidence in the recording - count them as false positives (effective 8/111, 7%).  The other four
(MV18 modern car seen from afar, H02 chair through the tabletop, S11 vending-machine popping, S14 bin moved) are real
detections beyond the heuristic's distance limits, as in the three.js run.  Typical unmatched reports: floating fence
posts / stall counters from oblique views, upside-down staircases and barriers, tree scale, shadow and culling claims.
Bottom line for the paper: with the VLM agents' farther starts and 3x regions, the 1.2B Open-P2P explorer rarely reaches
the planted object within 60 s of simulated time; the Unreal VLA arm is a lower bound driven by exploration coverage, not
by the judge.

## VLA arm, audit stage through the native harness (2026-09-20): `--replay-mode vqa`, Gemini and Claude Code

Owner's decision after the cost measurements: the VLA arm's auditor is the same native CLI harness as the embodied arm
(prompt, subcategory ICL, scene text, judge-input rule), reduced to one answer - `read_example`, `observe` (all 120
recorded frames at 480x288 + the explorer's track) and one `report` call; no environment actions, no inspect.  Rejected
on cost (same six episodes, gemini-3.8-flash): 40 segment plays $2.96 / episode, 2 s preview + inspect $0.89, all frames +
notes tools $0.54; vqa $0.24 (embodied $1.03).  Gemini charges ~1100 tokens per image at any size, so cost = frames in
context x model calls.  Full write-up: `reports/vla-vqa-20260920.md`; results for the GPT-6 judge in `~/vla-results/`.

| auditor (vqa) | Unreal 111 | Urban 15 (IPC-fixed builds, recorded 2026-09-20) | cost / episode |
|---|---:|---:|---:|
| gemini-3.8-flash medium | 10/111 (estimate, Gemini text judge) | 0/15 | $0.24 |
| claude-opus-5 effort medium (= pure Opus 5 batch) | 7/111 | 1/15 | $0.64 |

Urban explorer batch `runs/vla-ue-urban-v1`: 15/15, start checks exact, closest approach 24 m median, exposure 1/15.
GPT-6 binary judge pending (Codex login); the estimates above are not the paper's numbers.
