# `agent/vlm/` - tool-calling VLM harness for embodied bug hunting

A second-generation harness for the bug-hunt benchmark: environment-agnostic, turn-based, driven by
native tool calling, with an append-only context (prefix-cache friendly), lossless frame memory,
a revisable bug ledger and two independent "temporality" axes (observation density, decision
granularity). The original `agent/vla/` stays frozen for reproducing the published results; the two
share the task definitions (`agent/vla/tasks.py`), the environments (`environments/threejs/runtime/`) and the scorer
(`judge/judge_sem.py`).

Design history and rationale: [`../PLAN-agent-agent.vla.md`](../PLAN-agent-agent.vla.md).

## Contents

1. [Quick start](#quick-start)
2. [How an episode runs](#how-an-episode-runs)
3. [Tools the model gets](#tools-the-model-gets)
4. [What the model sees](#what-the-model-sees)
5. [Decision granularity: macro vs tick](#decision-granularity-macro-vs-tick)
6. [Memory: archive, inspect, history, notes, compaction](#memory-archive-inspect-history-notes-compaction)
7. [Bug ledger](#bug-ledger)
8. [Environments](#environments)
9. [Models and servers](#models-and-servers)
10. [CLI reference](#cli-reference)
11. [Outputs](#outputs)
12. [Scoring and the dashboard](#scoring-and-the-dashboard)
13. [Ablation switches](#ablation-switches)
14. [Tests](#tests)
15. [Known limitations and pending work](#known-limitations-and-pending-work)

## Quick start

```bash
# one-time (repo root)
python3 -m venv .venv && .venv/bin/pip install playwright requests pillow numpy imageio imageio-ffmpeg pytest
.venv/bin/playwright install chromium
bash scripts/fetch_assets.sh          # three.js vendor files + Sponza (+ dungeon); the house needs assets/house/pack

# a model: local vLLM ...
bash scripts/serve_model_tools.sh qwen8b 3                      # tool calling + prompt-token details + big mm cache
# ... or any OpenAI-compatible endpoint, e.g. OpenRouter (key via env var, never on the command line)
export VLM_API_KEY=$(cat ~/.config/openrouter/key)

# one episode (the corridor needs only the vendor assets; SP/HS need Sponza / the house pack)
.venv/bin/python -m agent.vlm.runner --task audit_tc10_bug --seed 0 --env threejs --gpu swiftshader \
  --obs final --model qwen/qwen3.8-flash --base-url https://openrouter.ai/api/v1 --tag smoke

# a grid, then the unchanged scorer and the dashboard
.venv/bin/python -m agent.vlm.runner --grid audit_sp05_bug,audit_sp00_clean --episodes 3 --parallel 2 \
  --tag agent-sp05 --model Qwen/Qwen3-VL-8B-Instruct --base-url http://localhost:8010/v1
.venv/bin/python -m judge.judge_sem runs/agent-sp05 --out reports/agent-sp05.md
.venv/bin/python -m agent.vlm.dashboard runs/agent-sp05 --open
```

`--gpu gl-egl` (default) uses the NVIDIA GPU through ANGLE/EGL on the Linux servers (no X server
needed; in Docker set `NVIDIA_DRIVER_CAPABILITIES=graphics,utility,compute`). On a Mac use
`--gpu native`: Playwright's headless_shell is software-only, but the full Chromium binary in the
new headless mode renders through ANGLE Metal on the Apple GPU (Sponza ~120 fps, actions in real
time; SwiftShader is ~7x slower than real time and shares one CPU budget across parallel
instances). `python -m agent.vla.bridge --check-gpu` prints the renderer string per mode. Rendering
speed never changes what the model sees: the world runs on a simulated clock that only advances
inside actions.

## How an episode runs

```
reset -> [system] [user: task + start view a0]
loop:
  model call  (tools attached, tool_choice=auto)
  -> assistant message appended verbatim (its text + tool calls)
  -> every tool call executed in order; each result appended as a tool message,
     images (observations, inspect recalls) appended as a user message right after it
  -> stop when: done was called | action budget used | sim-time budget used | call cap hit
  -> compaction when the predicted prompt exceeds --context-limit (see Memory)
```

- There is no notion of "step": the loop is a flat tool loop. Environment actions are numbered
  `a1, a2, ...` (the *action index*) for frame references and budgets; memory and bug tools do not
  consume budget.
- Several tool calls in one reply are fine. Environment actions among them run sequentially and each
  returns its own observation, so a model that chains `turn` then `move` acts blind for the second one.
- Budget: `--max-actions` (default 100; `task` = the task's own `steps` from `agent/vla/tasks.py`, e.g. 25
  for SP) and `--max-calls` (hard cap, default 400).
  `--max-sim-seconds` adds a simulated-time budget usable in both decision modes.
- A reply without any tool call is nudged once ("reply with a tool call"); a second one is retried
  with `tool_choice=required`; a third ends the episode with outcome `no_action`. Providers that
  reject `required` (Qwen thinking mode on OpenRouter returns 400) fall back to `auto` for the rest
  of the episode.
- Thinking models can spend the whole output budget on hidden reasoning and return nothing
  (`finish_reason=length`, no tool call). Such a reply is not appended; the call is retried with
  a doubled `max_tokens` (at most 4x, twice).

## Tools the model gets

Tool schemas are OpenAI function-calling JSON (`agent/vlm/tools.py::tool_schemas`). Environment actions
are filtered by the adapter's capabilities; the other groups by `--tools`.

| tool | arguments | effect | consumes budget |
|---|---|---|---|
| `move` | `distance_m` 0.3-4, `direction` forward/back | walk; stops early at obstacles | yes |
| `turn` | `degrees` -180..180 (+ = right) | turn in place (120 deg/s) | yes |
| `look` | `degrees` -90..90 (+ = down) | tilt the view | yes |
| `interact` | - | use what is aimed at within ~3 m; the world runs 2.8 s to show delayed mechanisms | yes |
| `wait` | `seconds` 0.5-5 | stand still; the world keeps running (sensing action) | yes |
| `done` | `summary` | end the inspection | - |
| `inspect` | `refs` (1-4), `region` `[x0,y0,x1,y1]` in 0..1 | bring archived frames back at full resolution, optionally a zoomed crop | no |
| `history` | `from_action`, `to_action` (<= 40 apart) | text of what the model said, did and observed in those actions (works after compaction) | no |
| `flag_bug` | `description`, `category`, `status` suspect/confirmed, `evidence` refs | records a bug at the current position, returns `b<n>` | no |
| `update_bug` | `id`, `description?`, `status?` (suspect/confirmed/retracted), `evidence?` | revise, confirm or retract | no |
| `list_bugs` | - | the current ledger | no |
| `write_notes` | `text` | append one entry to the durable notes | no |

Tool groups: `memory` = inspect + history, `bugs` = flag_bug + update_bug + list_bugs, `notes` =
write_notes. Errors (unknown ref, bad id, budget exhausted, no time left in the tick) come back as
`ERROR: ...` tool results, never as exceptions.

## What the model sees

**System prompt** (`agent/vlm/prompts.py::build_system`): QA role, the five-category bug taxonomy
(unchanged from the old harness), the action list for this environment, the observation format for
the chosen mode, the tick rules (tick mode), the memory / notes / ledger semantics for the enabled
groups, the optional expectation hint (`--expect`), and the rules. It is byte-identical across calls
and episodes of a run, so it stays in the shared cached prefix. The task instruction is the first
user message, together with the start view `a0`.

**Observation after an environment action** = one tool message (text) + one user message (images):

```
a12 move forward 2.0m -> moved 1.98m | pos (x=1.20, y=-0.30) yaw 90 pitch 0 | sim +0.4s | frames: a12.f0..a12.f3 (film), a12 (final)
[observation a12]  a12.f0 t=+0.0s <img>  a12.f1 t=+0.5s <img> ...  a12 final view <img>
```

- `--obs final`: one full-resolution frame per action (960x576 in the context).
- `--obs film`: frames sampled every `--film-dt` simulated seconds during the action (max
  `--film-max`, 480x288 in the context) plus the final frame. Long actions (a 5 s wait, an
  interact) become a strip; a blocked move films a frozen view while the text reports the effort.
- `--proprio 1` (default) includes displacement, position, heading, pitch and the action echo.
  `--proprio 0` is the pure-vision channel: the text is only `a12 | frames: ...`; the compaction
  index and inspect captions drop positions as well. Positions and the obstruction flag stay in the
  logs for analysis.
- `--blocked-hint 1` appends `[BLOCKED - something invisible or solid is in the way]` when a move
  fell short by more than max(0.25 m, 10 %) (harness rule `agent/vlm/env/base.py::is_blocked`); off by
  default, and never shown with `--proprio 0`.

Image sizes are multiples of 32 so Qwen3-VL image-token counts are deterministic (960x576 = 542,
480x288 = 137 tokens). Every frame is archived at capture resolution regardless of what enters the
context (film frames are requested at 960x600 from the page).

## Decision granularity: macro vs tick

`--decision macro` (default): each action runs to completion (a 45 deg turn takes 0.375 s of
simulated time, a 4 m move 0.77 s, a wait up to 5 s, an interact 2.8 s) and the model cannot
intervene meanwhile.

`--decision tick --tick 0.5`: every decision that acts advances exactly one tick of simulated
time. Same tools; the schema maxima shrink to what fits in a tick (move <= 0.9 x 5.2 m/s x tick =
2.34 m, turn/look <= 60 deg, wait = one tick), the actions in one reply share the tick in order,
the last one holds the agent still to the tick's end, `interact` triggers a mechanism that keeps
running through later ticks, and memory / bug tools take no time.

- A request longer than the tick is clamped, and the observation says so:
  `[tick limit: you asked for 4.0 m, 2.34 m fits in one 0.5 s tick; that part ran and the tick is
  over - decide again: continue the same action or choose another]`. Moves are clamped by distance
  (not cut by time) so a clamped move never looks like an obstruction.
- A request shorter than the tick runs, then the agent idles to the tick's end; the observation is
  the view at the end of the tick.
- A second action that no longer fits gets `ERROR: no time left in this tick ...`.
- Tick mode delivers one frame per tick (`--obs film` is rejected). Compare `(macro, film)` with
  `(tick, final)`: the same 2 fps of pictures, different decision rate.
- Use `--max-sim-seconds` to give macro and tick runs the same simulated-time budget.

Environment side: `act` takes `maxSec` (cut the action short) and `holdSec` (keep simulated time
running until this much has elapsed) - implemented in `environments/threejs/runtime/core.js`, the reef page and the shared
standalone-page contract (`environments/threejs/scenes/src/common/harness_page.js`); the UE contract has
`hold`. Standalone pages run on the wall clock, so their ticks are approximate.

## Memory: archive, inspect, history, notes, compaction

**Archive** (`agent/vlm/archive.py`): every frame is written to `frames/` at capture resolution and
indexed in `frames/index.jsonl` (ref, file, kind, sim time, action, pose). Refs: `a12` = final view
of action 12, `a12.f3` = film frame 3 of action 12, `a0` = start view. Data URLs sent to the model
are encoded once and reused byte-for-byte (the server's prefix cache hashes image pixels).

**inspect** returns the original JPEG (or a crop scaled to <= 960 px, sides multiples of 32) in a
user message; captions carry the action, kind, time and, with proprio on, the pose. Crops are
archived too (`a18#c1` = first crop of a18, file `a018_c01.jpg`, index rows of kind `crop` with
the region), so the transcript and the dashboard show exactly what the model saw. **history**
returns one line per action in the range: the model's own text at the time, the action and the
observation text - it works for actions that compaction has dropped from the context.

**Notes** (`agent/vlm/notes.py`): `write_notes` appends a line to `notes.md`. Notes are the model's
durable memory and are what compaction carries over.

**Compaction** (`agent/vlm/context.py`): the conversation is strictly append-only, so within an epoch
every request extends the previous one. The next prompt size is predicted from the last measured
`prompt_tokens` plus an estimate of what was appended (text at 4 chars/token, images by the
32-pixel rule, the tool schemas once); per-call drift is logged. When the prediction crosses
`--context-limit` (64k):

1. the model is asked, with its current notes quoted, to **rewrite the notes** as a continuation
   state (progress, areas covered / not, suspicions with frame refs, judgement on flagged bugs,
   plan; <= ~300 words); the reply replaces `notes.md` (a copy goes to `context/note_N.md`);
2. the old messages are saved to `context/epoch_N.json`;
3. the context is rebuilt as `[system] [user: task + notes + action index + bug ledger]` followed
   by the last `--keep-recent` (3) environment actions' messages verbatim.

The action index is one line per action (what, displacement, pose, blocked, frame refs) so the model
knows which refs to inspect. Compaction never happens twice in a row; if the tail alone exceeds the
limit the loop proceeds anyway. The note request itself may exceed the limit by one observation,
so the server's `max-model-len` needs headroom (98k for a 64k limit).

## Bug ledger

`flag_bug` records `{id, description, category, status, evidence, pos, action, simT}`; evidence
refs must exist in the archive. `update_bug` changes description / status / evidence; `retracted`
is terminal. Every change is appended to `bugs.jsonl`. `meta.json.flags` exports the final
non-retracted entries in the old `{pos, note, simT}` shape plus the ledger fields, which is what
`judge/judge_sem.py` scores (it reads `note`; `suspect` and `confirmed` are treated alike).

## Environments

| `--env` | adapter | notes |
|---|---|---|
| `threejs` (default) | `agent/vlm/env/threejs.py` over `agent/vla/bridge.py` | opens `environments/threejs/runtime/agent.html?config=<name>` for core.js configs (env0 corridor, TC, SP Sponza, HS house) or the standalone page a config names in its `page` field (WT reef, AF airfield, WL wilderness, CT cottage). Capabilities: move, turn, look, interact, wait. |
| `ue` | `agent/vlm/env/ue.py` | HTTP client for `simworld_server`; the turn-based contract (`clock: "tick"`, `film`, `hold`, `moved`, `sim_elapsed`) is documented in the module docstring and is **not implemented server-side yet**. Capabilities: move, turn, wait. Positions converted from cm. |
| `fake` | `agent/vlm/env/fake.py` | synthetic plane with an optional invisible wall, for tests and dry runs |

The adapter contract (`agent/vlm/env/base.py`): `reset(config, seed, obs) -> Observation`,
`step(Action) -> Observation`, `capabilities`, `speed_mps`, `turn_dps`, `meta()`, `close()`.
Poses are metres and degrees in a harness frame (x, y horizontal; z up); `pose.raw` keeps the
environment-native values for the trajectory files.

Assets: env0/TC need `assets/vendor`; SP needs `assets/sponza`; HS needs `assets/house/pack`;
the standalone pages are the HTML builds from the GitHub release (`environments/threejs/scenes/BUILDS.md`).

## Models and servers

Any OpenAI-compatible endpoint (`agent/vlm/llm.py`): `--base-url` / `VLM_BASE_URL`, `--model` /
`VLM_MODEL`, key from `VLM_API_KEY`. Non-streaming; assistant messages are normalized to
`role/content/tool_calls` before being appended.

Defaults follow Qwen's thinking-model recommendation: temperature 1.0, top_p 0.95, top_k 20,
min_p 0, presence 0, repetition 1.0, `--max-tokens 4096` (hidden reasoning counts against it),
`--reasoning-effort low` (sent as the OpenAI top-level `reasoning_effort`, which DashScope and
OpenRouter honour - DashScope ignores the nested OpenRouter form; dropped for the session if the
server answers 4xx). Measured on qwen3.8-flash (DashScope): low ~0.9k reasoning tokens / 15 s,
medium ~1.5k / 29 s, xhigh (the server default) ~7k / 2 min on a hard prompt.

`--preserve-thinking on` (default) re-sends the model's chain of thought (`reasoning_content`) with
its earlier assistant turns, which is Qwen3.8's chat-template default and the model card's
recommendation for agents ("decision consistency and reduced redundant reasoning"); `off` keeps
only the final text and tool calls (the older Qwen3 recommendation). Either way the chain of thought
is logged (`transcript.jsonl` assistant rows, `calls.jsonl` reasoning_chars, dashboard). Providers ignore what they do not support (OpenRouter drops `min_p` /
`repetition_penalty` for Alibaba). Usage records prompt / completion / cached / reasoning tokens.

vLLM (`scripts/serve_model_tools.sh`): `--enable-auto-tool-choice --tool-call-parser hermes
--enable-prompt-tokens-details --limit-mm-per-prompt '{"image":512}' --max-model-len 98304
--mm-processor-cache-gb 16`. Prefix caching is on by default; keep N parallel episodes x 64k of KV
resident or cross-call hits vanish.

## CLI reference

`python -m agent.vlm.runner`:

| flag | default | meaning |
|---|---|---|
| `--task NAME` / `--grid a,b` | - | one episode / a grid (`--episodes N` seeds per task, `--parallel P`, `--resume`) |
| `--seed`, `--tag` | 0, timestamp | seed; run directory `runs/<tag>/` |
| `--env`, `--gpu`, `--ue-url` | threejs, gl-egl | adapter; Chromium GPU flags (`vulkan`, `gl-egl`, `swiftshader`) |
| `--model`, `--base-url` | env vars | model and endpoint |
| `--obs final\|film`, `--film-dt`, `--film-max` | film, 0.5, 8 | observation mode |
| `--ctx-final`, `--ctx-film` | 960x576, 480x288 | in-context frame sizes |
| `--decision macro\|tick`, `--tick` | macro, 0.5 | decision granularity |
| `--max-actions`, `--max-calls`, `--max-sim-seconds` | 100 (`task` = task steps), 400, none | budgets |
| `--rate-limit-wait`, `--network-wait` | 3600, 1800 | seconds of HTTP 429 / connection-error retrying before an episode is abandoned |
| `--context-limit`, `--keep-recent` | 64000, 3 | compaction |
| `--tools` | memory,bugs,notes | tool groups (`none` to disable all) |
| `--expect on\|off` | on | "state your expectation before acting" hint |
| `--proprio 0\|1`, `--blocked-hint 0\|1` | 1, 0 | proprioceptive text; obstruction hint |
| `--temperature`, `--max-tokens`, `--top-p`, `--top-k`, `--min-p`, `--presence-penalty`, `--repetition-penalty`, `--reasoning-effort` | see above | sampling |
| `--thinking-budget N` | none | hard cap on reasoning tokens per call (DashScope `thinking_budget`; 0 = thinking off). Measured on qwen3.8-flash: effort low/medium do not bound reasoning (6-9k tokens, 2-3 min on a hard prompt); budget 300 -> 8 s, 1000 -> 18 s, off -> 3 s |
| `--no-video` | - | skip `video.mp4` |

Tasks are the audit tasks of `agent/vla/tasks.py` (`audit_<case>_<variant>`; variants `bug`,
`clean`, and the ladder `l1`/`l2`/`l3`).

## Outputs

`runs/<tag>/<task>-p<proprio>-s<seed>/`:

| file | content |
|---|---|
| `meta.json` | config, outcome, budgets used, usage (with cached and reasoning tokens), `flags` (scoring), `bugs_history`, tool counts, renderer, page errors |
| `transcript.jsonl` | every message the model saw, in order; images as `{"type":"image_ref","ref":...}`; assistant rows carry `call`; compaction rows are `{"event":"compaction","epoch":N}` followed by the new header |
| `calls.jsonl` | per model call: kind, tool_choice, tools called, prompt / completion / cached / reasoning tokens, predicted prompt and drift, latency, finish reason |
| `actions.jsonl` | per environment action: index, issuing call, action, displacement, pose, blocked, events, sim time, frame refs, the model's text |
| `frames/` + `frames/index.jsonl` | the archive |
| `bugs.jsonl`, `notes.md` | ledger events; the notes |
| `context/epoch_N.json`, `context/note_N.md` | the messages dropped at compaction N; the rewritten notes |
| `trajectory.jsonl`, `frames.jsonl`, `video.mp4` | old-harness shapes for `judge/metrics.py`, `judge/plot_traj.py`, `judge/video.py` |

## Scoring and the dashboard

`python -m judge.judge_sem runs/<tag>` works unchanged: it reads `meta.json` (task name, config,
model, `flags[].note`), asks the judge model whether each note describes the planted bug, counts
at most one true positive per episode, and treats every flag in a clean episode as a false positive.
`judge/adjudications.json` overrides remain in force.

`python -m agent.vlm.dashboard runs/<tag> --open` (or `runs`, recursive) writes a self-contained
`index.html` next to the runs (frames referenced in place): a run grid with outcome, flags, tool
usage chips, cache hit rate; per run the configuration, a top-down path (blocked steps red, flags as
diamonds), the final ledger with clickable evidence refs, usage, notes, and the full transcript call
by call - the model's text, each tool call with its result, film strips and final frames, inspect
recalls, flag / update badges, notes, compaction events with the rewritten notes.

## Ablation switches

| question | compare |
|---|---|
| observation density | `--obs final` vs `--obs film` (macro) |
| decision granularity | `--decision macro --obs film` vs `--decision tick --obs final` at equal `--max-sim-seconds` |
| proprioception | `--proprio 1` vs `--proprio 0`; `--blocked-hint 1` as the injected-aid reference |
| memory tools | `--tools memory,bugs,notes` vs `--tools bugs` (no inspect / history / notes) |
| notes | `--tools memory,bugs` (compaction still rewrites notes, the model just cannot append) |
| expectation hint | `--expect on` vs `off` |
| context | `--context-limit`, `--keep-recent` |

## Tests

```bash
.venv/bin/pytest -q -m "not chromium and not live"    # unit: fake env + scripted model (~100 tests)
.venv/bin/pytest -q -m chromium                        # three.js adapter, tick caps, runner end-to-end on env0
VLM_BASE_URL=... VLM_MODEL=... .venv/bin/pytest -q -m live -s agent/vlm/tests/test_live.py   # real model: tool calls, cache hits, drift
```

## Known limitations and pending work

- The UE side is client-only: `simworld_server` still runs the world in real time; the tick-mode
  step (`UnrealCV vset /action/game/pause` + `vset /action/tick`), `film` and `hold` are specified
  in `agent/vlm/env/ue.py` and not implemented.
- Standalone pages (reef, airfield, wilderness, cottage, packed house / Sponza) run on the wall
  clock; their built HTML files must be rebuilt from `environments/threejs/scenes/src` to pick up
  `maxSec` / `holdSec` (tick mode) and `filmW` / `filmH` (full-resolution film frames).
- Frames are JPEG (final 0.85, film 0.7 from the page): every frame is kept, but not pixel-exact.
- Thinking models cost 5-90 s per call; tick mode multiplies the number of calls. Use the
  8B / 30B models on vLLM for grids and reserve thinking models for representative cases.
- Token prediction assumes Qwen3-VL's 32-pixel image tokens; other model families change the
  compaction trigger point (drift is logged per call).
