# Native model clients with shared MCP tools

Two starters use the same `world_audit` stdio MCP server:

| Starter | Native agent client | Exact default model | Authentication |
|---|---|---|---|
| `scripts/native-agents/start_gpt6.sh` | Codex CLI | `gpt-6-astra` | Existing ChatGPT login; API fallback disabled |
| `scripts/native-agents/start_gemini.sh` | Gemini CLI | `gemini-3.8-flash` | Google login by default; explicit Gemini API-key option available |
| `launch.py claude ...` | Claude Code (`claude -p`, strict MCP config, built-in tools off, Stop hook = completion guard) | `claude-opus-5` | Existing claude.ai login; API key removed from the child environment |
| `launch.py qwen ...` | Qwen Code (`qwen --auth-type openai`, OpenAI-compatible endpoint from `--qwen-base-url`, built-in tools off, Stop hook) | `qwen3.8-flash` | API key file (`--qwen-api-key-file`), Token Plan endpoint by default |
| `launch.py opencode ...` | OpenCode (`opencode run --format json --pure --auto`, private `opencode.json`: OpenRouter provider, only the world_audit MCP server, built-in tools off) | `openrouter/meta/muse-spark-1.3-contributor` | `OPENROUTER_API_KEY` from `--opencode-api-key-file`; never written to disk |
| `launch.py muse ...` | Muse Code (`muse exec --json`, private XDG config; `--muse-base-url` routes the Meta provider elsewhere) | `muse-spark-1.3` | Meta login (auth.json) or `META_API_KEY` from `--muse-api-key-file`. Muse Code inlines at most 4 images per tool result and 50 per request, so the 120-frame vqa protocol does not fit it; kept for reference |

Each run starts **one native CLI process for the whole episode**. The client owns
model calls, conversation history and compaction. There is no per-action CLI restart,
session-resume loop or outer Python LLM driver. The MCP process owns the environment,
image archive, action budget, bug ledger and notes. Native clients can differ in
reasoning and compaction; this evaluates model + native harness.

## Setup

From the repository root:

```sh
python3 scripts/native-agents/setup.py
codex login status
gemini
```

The last command opens Gemini CLI for Google sign-in if needed; exit after signing in.
Existing global client settings and credentials are not overwritten. Codex uses
`exec --ignore-user-config`, retaining its existing auth. Gemini receives a settings
file through a process-local `GEMINI_CLI_SYSTEM_SETTINGS_PATH`; only `world_audit`
is allowlisted, built-in tools are disabled, and extensions are disabled for this run.
Codex shell, image-file, web and delegation tools are disabled; its remaining native
bookkeeping is client-managed. The task prompt requires all environment access via MCP.

The setup installs a local Python environment. Shared `Dispatcher`, `FrameArchive`,
`BugLedger`, `Notes`, and tool schemas are included in this repository's `agent/`
package; a separate private upstream clone is no longer required. The imported
agent Python files were checked byte-for-byte against the AWS pinned dependency.
`upstream.json` preserves its historical source revision. Run manifests record
the bundled code digest, and the launcher verifies every agent source file against
`upstream.json` before running an episode.
It does not run `agent.loop`. Installed versions are recorded in
`out/native-agents/installed-requirements.txt`.

Model names are passed verbatim. Gemini API-key access was verified in this
workspace; new accounts must have access to the requested model. There is no
launcher fallback to another model.

## Start a real Unreal episode on AWS

The public review website is **not** an agent `/step` endpoint. The helper below
reads the deployed catalog, finds the matching immutable task build and checks its
binary hash, then starts a separate paused Unreal process on a spare GPU. It neither
changes production configuration nor writes annotations to production databases.

In terminal A:

```sh
python3 scripts/native-agents/connect_unreal.py \
  --host ec2-user@98.84.22.147 \
  --identity /path/to/a10_4.pem \
  --task S05 --gpu 2 --local-port 19100 --remote-port 49100
```

Use the actual private-key path or an SSH host alias with a configured identity.
This workspace also has an ignored local `out/native-agents/aws-connection.json`
recording the previously located WeChat key's path, so here `--host` and `--identity`
can be omitted. It stores a file path, never the private key contents.
The helper copies only the environment bridge/viewer into a versioned
`~/native-agent-mcp/code-<hash>/` directory. Episode files go under
`~/native-agent-mcp/episodes/`. The key remains on the client machine.
GPU selection refuses production-owned GPUs. By default it requires an idle GPU.
For two episodes on one spare GPU, pass `--gpu-slots 2 --gpu-slot 0` and
`--gpu-slots 2 --gpu-slot 1` to two helpers with distinct ports. A shared GPU lease
and exclusive slot leases prevent duplicate ownership; admission checks require
at least 6 GiB free and reject occupied GPUs without a sibling runner lease. Current AWS production owns
GPUs 0/1; the helper checks this again each time. The HTTP endpoint binds to server
loopback and is reached through SSH; no new public firewall rule or TURN is needed.

When it prints `Ready`, use terminal B for **one** of:

```sh
bash scripts/native-agents/start_gpt6.sh \
  --environment unreal-http --env-url http://127.0.0.1:19100 \
  --task S05 --max-actions 40 --observation on-demand --allow-icl-overlap

# Run this only after stopping/restarting terminal A for a fresh S05 episode:
bash scripts/native-agents/start_gemini.sh \
  --environment unreal-http --env-url http://127.0.0.1:19100 \
  --task S05 --max-actions 40 --observation on-demand --allow-icl-overlap
```

Ctrl-C in terminal A stops its private game and SSH tunnel. Each model must receive
a **fresh episode**. Do not point two clients at the same environment endpoint.
S05 is already an ICL example; the commands use it for setup/connection checks,
not as a held-out evaluation task. Choose an eligible held-out task for scored runs.
For parallel comparisons start a second helper on spare GPU 3, with distinct local
and remote ports, e.g. 19101/49101, and use that URL for the second model.

Existing native builds accept seed slot 0 but do not explicitly seed startup RNG.
The manifest records this limitation; same task/build/start does not establish
perfectly deterministic replay. The bridge requires paused observations and reports
native simulation time. A transport error stops further actions rather than retrying
an uncertain action with a different request ID.

The helper supports the deployed AWS catalog format and native `?Task=` entries.
This is not a claim that every task/build has been tested with the agent interface.

## Same MCP tool contract

| Group | Tools |
|---|---|
| Visual demonstrations | `read_example` (definition, images, reference answer; required before scene access) |
| Start / current observation | `observe` (lazy start, then cached view; includes notes and ledger) |
| Environment actions | `move`, `turn`, `look`, `interact`, `wait` |
| Visual / text memory | `inspect`, `history`, `write_notes` |
| Bug reports | `flag_bug`, `update_bug`, `list_bugs` |
| Finish | `done` |

`read_example` and `observe` are the added demonstration/lifecycle tools; it starts only the operator-assigned
task. Models cannot reset into another task, read rubrics or list private ground truth.
Discovery (`tools/list`) never starts a game. Every run exports `episode/tools.json`
and its hash, allowing the two clients' exact schemas to be compared.

- Default **40 environment actions**; enforced in MCP, independent of the client.
- Memory/report tools take no action budget but do cost tokens and tool calls.
- Default **400 MCP tool calls**; after the cap only `done` is allowed.
- No simulation advancement during `inspect`, `history`, notes or reports.
- This initial MCP adapter uses complete (macro) actions. Upstream's fixed-tick
  decision ablation is not exposed by these starters.
- `inspect` returns 1–4 selected archive frames, optionally cropped.
- `history` returns up to 40 actions' tool/observation text. It cannot access the
  native client's private reasoning or messages that were never sent to MCP.
- `write_notes` appends durable notes; `observe` can retrieve them after native
  context compaction. MCP cannot delete images from the native client's context.
- `confirmed` is the inspecting model's own claim, not the human acceptance label.
- `done` finalizes the local bug ledger. Grading with private rubrics is separate.

## Image delivery

| `--observation` | Capture/archive | Images initially sent after each action |
|---|---|---|
| `on-demand` (default) | Intermediate frames at native 0.5 s intervals, capped at 8, plus final | Final image plus available frame IDs; select more with `inspect` |
| `film` | Same | All sampled images (smaller) plus final image |
| `final` | Adapter retains only final | Final image only |

The native Unreal service may still capture intermediate images in `final` mode;
the adapter discards them. This flag controls model-visible/archive observations,
not a claim of reduced GPU capture work. Intermediate frames are bounded samples,
not every rendered frame. Native capture timing includes the action endpoint, so
frame counts depend on action duration and endpoint sampling.

Archive refs follow upstream: `a0` is the start, `a12` the final frame of action 12,
`a12.f3` an intermediate sample. MCP returns actual `image` content blocks, not
unreadable server paths or base64 embedded in text. Crop operations are archived too.

## Environment description

The initial user prompt includes an `Environment description` section before the
MCP workflow instructions. `observe` also returns it alongside notes and the bug
ledger, so it remains retrievable after native context compaction.

`scripts/native-agents/task-scenes.json` contains a snapshot of the public AWS review
page's scene descriptions, with `task.scene_i18n` as its fallback. It covers all 250
catalog tasks and their case aliases. Only scene setting, public object/context text
and normal interactions are copied; task bug descriptions and private rubrics are
not read into this field. The previous local scene-description file differed from
the live site's A09 text, so this snapshot uses the live public description.

Use `--scene-catalog /path/to/catalog.json` to select an updated snapshot, or
`--scene-description-file /path/to/public-description.txt` for an explicit task
background. The catalog format is `{"scenes": [{"task_ids": ["A09"],
"description": {"en": "Public scene description"}}]}`. Real environments fail startup
when their description is missing. Synthetic smoke environments receive an explicit
synthetic description. This works with both task-specific ICL and `--no-icl`.

The exact text is saved in `episode-config.json`, `launch.json`, and episode metadata,
and is included in the prompt/protocol hashes used for model comparisons.

## Task-specific in-context example (enabled by default)

**Each task receives exactly ONE example matching its specific subcategory.**
A C3 task gets only the C3 definition, three ordered images and reference answer;
a G1 task gets only the G1 example. The library contains 15 examples / 29 images,
but the other examples are not copied into that run or exposed through MCP.

The launcher resolves the task's subcategory from
`scripts/native-agents/task-subcategories.json`, a snapshot of AWS task IDs,
case aliases and subcategory labels. No rubrics, bug locations or task answers are
included in this map. Known task labels must agree with any explicit override.
For new tasks, supply `--subcategory C3` or `--task-catalog /path/to/map.json`.
The catalog format is `{"task_subcategories": {"task-id": "C3"}}`; update it when
task labels change. The map selects the example and is not passed to the model.

The native client must call `read_example()` (or use its assigned code) before
`observe` or any scene/report tool. It receives a category definition, 1–3 original
image content blocks with figure captions, and a labeled reference answer. It may
re-read the SAME example after context compaction. Other category codes are rejected
by the tool schema. Delivery uses MCP tool-result context, not imported synthetic
user/assistant turns in a client's private session history. In code mode, forward
image blocks with `image(block)` rather than JSON/text serialization.

The example read does not start/reset the scene or consume the 40 environment
actions. It consumes one MCP call and model input tokens. Original image bytes and
resolution are preserved; native clients still control preprocessing and compaction.

Each run snapshots only its selected public example and images under `<run>/icl/`,
along with the evaluation exclusion list. Review metadata and grading rubrics are
not copied. The selected subcategory, counts, content hash and prompt hash are
recorded in `launch.json` and the shared protocol hash. MCP logs `icl:CODE:N` refs;
these are separate from scene frames and cannot be used as current bug evidence.

- `--icl-dir /absolute/path/to/pack`: use another library with `context.json`, its
  image files and `exclude_from_eval.json`.
- `--no-icl`: explicit zero-shot ablation.
- Missing task labels or missing matching examples stop startup; there is no
  fallback to all examples, another category or zero-shot. In particular, the
  current pack has no S1 example.
- ICL demonstration tasks and listed aliases are excluded from evaluation.
  `--allow-icl-overlap` allows deliberate connection checks and marks the run
  `evaluation_eligible: false`.
- Image assets are ignored by Git. Copy the public example library to a new machine
  or specify `--icl-dir`; the launcher then selects only the matching example.

Examples (configuration only, no model or game started):

```sh
bash scripts/native-agents/start_gpt6.sh --environment fake --task smoke --subcategory C3 --dry-run
bash scripts/native-agents/start_gemini.sh --environment fake --task smoke --subcategory C3 --dry-run
bash scripts/native-agents/start_gpt6.sh --environment fake --task smoke --no-icl --dry-run
```

## Preparation and smoke tests

Write all configs without starting a model/game:

```sh
bash scripts/native-agents/start_gpt6.sh --environment fake --task smoke --subcategory C3 --dry-run
bash scripts/native-agents/start_gemini.sh --environment fake --task smoke --subcategory C3 --dry-run
```

Explicit synthetic model smoke test (not a benchmark result):

```sh
bash scripts/native-agents/start_gpt6.sh --environment fake --task smoke --subcategory C3 \
  --max-actions 2 --max-tool-calls 20 \
  --instruction 'Synthetic transport test: observe, wait 0.5 seconds, inspect a0 and a1, then done. Do not flag bugs.'
```

Replace the starter with `start_gemini.sh` for Gemini, after authentication.
For explicit Gemini API-key login, export `GEMINI_API_KEY` outside the script and
add `--gemini-auth gemini-api-key`. Alternatively add `--gemini-api-key-file /path/to/private/key`
to load the key into only the child process environment. The launcher never copies
the credential into prompts, manifests, command arguments or generated settings.
This still uses Gemini CLI's native agent loop, not our own API loop.

Protocol tests:

```sh
out/native-agents/venv/bin/python -m pip install pytest
out/native-agents/venv/bin/python -m pytest -q tests/test_native_mcp.py
```

## Outputs and comparison

Every launch creates a new directory under `out/native-agents/runs/`, or use
`--run-dir <new-empty-directory>`:

- `launch.json`: exact requested model, native command/version, shared protocol hash,
  process result and whether MCP actually completed the episode.
- `prompt.txt`, `episode-config.json`: reproducible operator configuration.
- `icl/`: frozen public demonstration pack; absent with `--no-icl`.
- `codex-overrides.json` or `gemini-settings.json`: generated client configuration.
- `native-events.jsonl`, `native-stderr.log`: client output, including client-reported usage.
- `episode/mcp-calls.jsonl`: tools, arguments, visible text and delivered image refs.
- `episode/actions.jsonl`, `frames/`, `bugs.jsonl`, `notes.md`, `meta.json`: common trajectory,
  visual evidence, report history and final flags.

Native usage fields can differ; MCP calls alone are not enough to estimate model
tokens. A successful CLI exit without MCP `done` is marked failed. Reusing a started
episode directory is rejected so a client reconnect cannot silently reset the task.

For fair comparisons hold task/build, action budget, observation mode, capture rate,
prompt/ICL and tool schema constant. Codex defaults to reasoning effort `low`;
Gemini is explicitly configured with `--gemini-thinking medium` by default; `low`
and `high` are also supported. The effective request is set through native CLI
`modelConfigs.customOverrides` / `generateContentConfig.thinkingConfig.thinkingLevel`
and the requested level is recorded in `launch.json`. ICL is enabled by default as described below;
`--prompt-file` still supplies task instruction text, not image attachments.

## VLA recordings: the same harness reviews a recorded exploration (`--environment vla-replay`)

The VLA arm's audit stage runs the SAME native client, prompt, ICL example, observation mode, action budget, tool
budget and judge as the embodied batches, on a recording of the Open-P2P explorer (`runs/<tag>/<TASK>/` from
`harness/vla_ue.py` or `harness/vla_explore.py`: `meta.json`, `poses.jsonl`, one frame every 0.5 s; frames can be
restored from `video.mp4` with `tools/vla_frames_from_video.py`).  The adapter is `auditor/mcp_agent/replay.py`.

| Embodied episode | Recording episode |
|---|---|
| `move`, `turn`, `look`, `interact`, `wait` | `play(from_s, to_s)`: any segment of at most 4 s, in any order, repeatable |
| `observe` = start view `a0` | `observe` = frame 0 as `a0` plus low-resolution preview frames every 5 s (`a0.f0..`) |
| final view per action; 0.5 s film frames archived (on-demand) | view at `to_s` per play; the segment's 0.5 s frames archived (`a<N>.f<k>`) |
| `moved`, pose, sim time per action | explorer's path length, recorded pose, and `explorer input: forward X s, back Y s` per play |
| 40 environment actions, 400 tool calls | 40 plays, 400 tool calls (`--require-full-budget` and the AfterAgent hook unchanged) |

Three replay modes (`--replay-mode`):

- `vqa` (the VLA arm's setting, chosen 2026-09-20): the harness is only a wrapper around a single answer. Tools are
  `read_example`, `observe` (start view, EVERY recorded frame inline at 480x288, the explorer's track) and `report(bugs,
  summary)`, which writes the bugs into the ledger through the pinned `flag_bug` and finishes the episode; no inspect,
  notes, history or environment actions, so an episode is exactly three tool calls. gemini-3.8-flash: $0.23 per
  episode (0.33 M tokens), 22 % of an embodied episode; Claude Code / claude-opus-5 (`--client claude`, `--claude-effort`
  equal to the embodied Claude batch): about $0.7-0.8 at effort high. Claude Code needs `MAX_MCP_OUTPUT_TOKENS` raised
  (the launcher sets it), otherwise the observe result is cut after 14 frames.

- `all` (the VLA arm's cost setting): no environment action at all (`--max-actions 0`). `observe` returns `a0`, the
  explorer's track as text (pose, path length and held keys per 0.5 s frame) and low-resolution frames every
  `--preview-every` seconds (default 5; the batch uses 2 s = 30 inline frames); EVERY recorded frame is archived as
  `a0.f<k>` for `inspect` and evidence. gemini-3.8-flash charges about 1100 tokens per image at any size, so the cost
  is (inline frames + inspected frames) x model turns: measured on A05, 0.5 s / 1 s / 2 s inline = $0.83 / $0.52 /
  $0.32 per episode against $1.03 for an embodied episode of the medieval batch.
- `play` (equal-budget reference): 40 `play` actions as described below; about 3x the cost of an embodied episode.

`play` is translated in the MCP server into a `seek` on the recording plus the pinned upstream `wait` action, so the
dispatcher, archive, `inspect` (with crops), `history`, notes and ledger are byte-identical to the embodied runs; the
model-facing tool list is `read_example, observe, play, inspect, history, write_notes, flag_bug, update_bug, list_bugs,
done` (`launch.json` records it, `episode/tools.json` its schema).  The system instructions replace the exploration
sentences with review sentences (`Episode.replay_instructions`).  Evidence refs are archive refs as usual, so the judge
input rule of the embodied batches applies unchanged.

```sh
out/native-agents/venv/bin/python scripts/native-agents/run_vla_replay.py --recordings runs/vla-ue-v1 \
  --batch out/native-agents/batches/<name> --tasks A05,I13 --key-file <gemini api key file> \
  --cli <gemini cli> --node-bin <node bin dir> --workers 4 [--stage agent|judge|all] [--resume] [--dry-run]
```

The runner writes `cases/<ID>/run/` (a normal launcher run directory), then grades each completed episode with
`eval.judge` (gpt-6-astra, medium; rubric = the task's `rubrics_i18n.en` from the mirrored AWS catalog, model output =
final ledger + done summary, images = the ledger's evidence frames in chronological order, else the first and last
view) into `cases/<ID>/judge.json`, and summarises `results.json` / `results.md`.  Tasks missing from the public
subcategory catalog (S22) take the catalog entry's subcategory and the public scene text of their map.  Protocol tests:
`tests/test_vla_replay.py`.

## Sources

- [Upstream tool contract](https://github.com/KimperYang/game-auditing/blob/d59b663ddb210414bc0cd5ce66cab0f0fd04f76a/agent/README.md)
- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Gemini CLI MCP](https://geminicli.com/docs/tools/mcp-server/)
- [Gemini CLI settings](https://geminicli.com/docs/reference/configuration/)

The installed Codex CLI is `0.154.0-alpha.6.2`; Gemini CLI is `0.34.0` at preparation.
The version of each actual run is recorded in `launch.json`.

## Verification on this workspace

- Protocol suite passes with a real stdio MCP client: discovery, image content,
  selected frame recalls/crops, delivery modes, action limits, bug retraction,
  notes, restart rejection, shared launch configuration and Unreal units/timestamps.
- `gpt-6-astra` / ChatGPT-authenticated Codex completed both a synthetic smoke run
  and a real AWS S05 run (`observe`, one 0.5 s `wait`, frame `inspect`, `done`).
  Logs: `out/native-agents/verification/codex-unreal-s05/`. This is connectivity
  evidence, **not** a bug-finding score or a 40-action benchmark.
- A separate direct MCP client verified the final real-backend adapter and build
  identity, without calling a model. Its directory is
  `out/native-agents/verification/final-mcp-unreal/`; the Gemini-generated config
  in that directory does not imply a Gemini model ran.
- Gemini API-key authentication and the exact `gemini-3.8-flash` model were
  verified through the native CLI. Google OAuth login was not tested here.
  The launcher stops before trying interactive login during a headless run.
- Private test episodes were stopped after verification; production services were
  left running and unchanged.

## Gemini API verification and pilot batch

Gemini CLI 0.34.0 successfully ran `gemini-3.8-flash` through the Gemini API with
MEDIUM thinking, received the three C3 demonstration images, observed the synthetic
scene, and called done. The installed native config resolver was checked to produce
exact model `gemini-3.8-flash` and `thinkingLevel: MEDIUM`. Logs are under
`out/native-agents/verification/gemini-api-icl-smoke/`.

`run_batch.py --batch <selection-directory> --key-file <private-file>` executes a
prepared `selection.json` on isolated spare GPUs, one new native CLI and game per
task. It checks task/build identity before launching, writes progress and task logs,
and stops each private game/tunnel after completion. The batch selection and grading
rubrics must remain separate from the agent workspace; the runner does not feed
rubrics to models. The current pilot requests all 40 actions unless the environment
fails. Provider configuration is native; there is no outer model-call loop.

The first ten-task pilot did not complete: S01 and R03 stopped after 8 and 33
actions without calling `done`, and later tasks failed the local port-availability
check. The launcher correctly records these as failed runs. To address these
failures, the revised runner uses a distinct port per task and supports
four slots (`gpus: [2, 3, 2, 3]`). Gemini now uses its native `AfterAgent` hook
to continue an incomplete episode in the same process and history, with bounded
continuations and no direct model calls from the hook. `--require-full-budget`
rejects early `done` calls unless the environment or tool budget has failed.
A synthetic native-CLI test deliberately ended after one of two actions; the hook
continued to two actions and `done`. Connectivity and protocol tests do not
establish real batch success.

The subsequent `gemini-medium-10-p4` pilot completed all ten episodes with exactly
40 actions and `done`: six target bugs were found under separate rubric grading.
The batch took 31.3 minutes (mean task wall time 9.6 minutes). Its estimated token
charges total $4.11, including native CLI auxiliary-model usage. These are local
experiment results; the private grades and artifacts are not committed.

### Full accepted batch and accounting

The 2026-09-17 review snapshot contains 74 accepted Unreal bug tasks and 64 accepted
Three.js bug tasks. The completed pilot's ten IDs are permanently excluded from the
remaining 128-task selection, including misses. Two accepted clean controls are
outside this injected-bug selection. Acceptance uses the platform's current-build
vote rules. `--resume` skips every task with an existing attempt directory, even
failed or interrupted attempts; a file lock prevents concurrent coordinators.

Four workers consume a shared queue. Unreal episodes use spare GPUs 2 and 3, two
slots each. Ten older Urban builds lack the native Auditor IPC interface and are
explicitly held with `--hold-task`; they are not model failures or completed runs.
The other 118 tasks are scheduled. Five tasks lack a matching ICL example or overlap
an example source: A21, S20, JS_SP13, JS_WT16 and JS_WT17. They run without ICL and
are labeled `zero-shot-exception`; summarize them separately from the ICL cohort.

Three.js uses the accepted production HTML pages, verified by SHA-256, in local
Chromium (Apple M4 in this run), with seed 5. It shares the same MCP action schema
and upstream action adapter. Browser pages use their native real-time animation
clock, including between model calls; this differs from paused Unreal IPC and is
recorded in metadata. Page answers/targets never enter the model context. A direct
MCP smoke test on all six clean control scenes verified initial images, actions,
film capture and completion without model calls or benchmark-task replay.

Each task stores wall time, environment startup time (Unreal), browser page-load
time, model process time, native CLI duration, token usage and estimated API cost.
`pricing.json` is snapshotted per batch. Cached prompt tokens are charged at the
cache rate, remaining prompt tokens at input rate, and generated tokens (including
the inferred thinking/other residual in CLI statistics) at output rate. Auxiliary
models use their own prices. Missing final usage or unknown models yield unknown
cost, never a fabricated zero; report totals cover only tasks with priced usage.
Prices are estimates, not invoices, and exclude infrastructure, taxes and credits.

`summarize_batch.py <batch> --serve 59861` serves a refreshed local report with
`results.json` and `results.csv`. Each completion also writes these files without
requiring the report server. Correct task execution and target recall are separate:
`completed` means MCP `done`; Found/Missed requires independent rubric grading.

The checked-in ICL metadata contains `context.json` and `exclude_from_eval.json`
under `examples/icl/`. The 29 referenced images are pending Hugging Face release
and must be restored under `examples/icl/images/` before running with ICL. See
[resource details](resources.md). Private review metadata, credentials, generated
run directories and provider logs are excluded from this code snapshot.
