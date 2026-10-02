# Reproducing the paper

This release is aligned with the **arXiv preprint** in Overleaf revision
`c808f5f8e87dee47d4de9fb44c467edd5e287bb7`, inspected on 2026-09-30.
Compiled environments and ICL images are available through the
[resource installer](resources.md). Source checks need no GPU; full model runs
require compatible hardware and model access. Original VLA recordings and frozen
ablation inputs remain pending.

## Evaluation set

Use `benchmark/paper-tasks.json` or the lists under `benchmark/splits/`.
The 213 assigned tasks comprise 126 Unreal and 87 Three.js cases. Counts by paper
family are 59 static physics, 41 interactive physics, 51 spatial consistency,
40 temporal consistency, and 22 semantic consistency.

`benchmark/tasks.json` is the separate 239-entry live review catalog, including
baselines. `services/review/tasks.json` is a 250-entry older fixture shipped with
that service. Neither is the evaluation split.

`paper_subcategory` and `paper_family` are aggregation labels. JS_WT16 and JS_WT17
are assigned to S2 in the paper, while their original missing prompt category and
zero-shot exceptions remain recorded. Do not change their original model inputs
when aggregating scores. Demonstration tasks are excluded from the evaluation set.

## VLM auditing

The paper uses 40 environment actions, on-demand observations, a matching anomaly
hint and in-context example, and one native client process per episode. Use
`--require-full-budget` and a fresh environment and output directory for every run.
Models are evaluated together with their native harnesses:

| Paper model | Client argument | Model argument |
|---|---|---|
| GPT-6 Astra | `codex` | `gpt-6-astra` |
| Claude Opus 5 | `claude` | `claude-opus-5` |
| Gemini 3.8 Flash | `gemini` | `gemini-3.8-flash` |
| Muse Spark 1.3 | `opencode` | `openrouter/meta/muse-spark-1.3-contributor` |
| Qwen 3.8 Flash | `qwen` | `qwen3.8-flash` |

Model IDs and defaults reflect the recorded experiments. Exact client versions,
authentication, and model availability must be supplied by the operator.
The paper uses medium reasoning settings; specify them explicitly because older
launcher defaults differ.

Install `subway` and `icl-examples` with `scripts/download_resources.py`, then run
`python scripts/serve_unreal.py --task S03 --port 19100` on your Linux GPU host.
In another terminal:

```bash
python scripts/native-agents/launch.py gemini \
  --environment unreal-http --env-url http://127.0.0.1:19100 \
  --task S03 --model gemini-3.8-flash --gemini-thinking medium \
  --max-actions 40 --max-tool-calls 400 --require-full-budget \
  --observation on-demand --run-dir out/runs/gemini-S03
```

For Three.js, install `threejs-builds` and use
`--environment threejs --task JS_AF01 --seed 5
--browser-config out/runtime/browser-profiles/JS_AF01.json`.
The config contains `browser_root`, `browser_page`, `browser_case`, and
`page_sha256`, as consumed by `auditor/mcp_agent/browser.py`. Use the original
seed and minimap masking configuration recorded for the experiment. Keep rubrics
and runtime profiles on the operator side of the MCP boundary.

See `native-agent-mcp.md` for tools, SSH setup and runtime behavior. AWS-specific
paths in imported scripts and profile snapshots require a local deployment mapping.

## VLA exploration followed by VLM analysis

Open-P2P 1.2B explores for 60 simulated seconds: 1,200 ticks at 50 ms, with a frame
recorded every 10 ticks (0.5 seconds). The resulting trajectories are shared across
VLM backbones. Runtime builds are available. Checkpoint setup instructions and original
trajectories remain pending.

```bash
python -m harness.vla_ue --tasks @benchmark/splits/unreal.txt \
  --profiles out/runtime/unreal-profiles.json \
  --ticks 1200 --dt-ms 50 --record-every 10 --size 1200M --tag vla-unreal
```

`harness/vla_explore.py` provides the Three.js explorer. Restore and remap the
profile snapshots in `benchmark/profiles/`, including the separate Urban IPC
profiles. These retain their original machine paths as provenance.

For recorded-trajectory analysis, the paper's single-report setting is
`--replay-mode vqa --max-actions 0`. The older interactive `play` replay mode is a
different protocol. `scripts/native-agents/run_vla_replay.py` coordinates analysis
and judging; `launch.py` also exposes replay for individual episodes.

## Judging

`eval/judge.py` scores the target anomaly using the report, cited evidence, and
English rubric. It returns a binary score and reason. Keep the assigned 213-task
denominator: unsuccessful executions count as failures.

```bash
python -m eval.judge --rubrics rubric.json --model-output report.json \
  --images evidence.png --output judge.json \
  --model gpt-6-astra --reasoning-effort medium
```

This command calls an authenticated model and is not part of offline tests.
`eval/judge_human_baseline.py` contains the human-baseline grading adapter;
participant submissions and identities are not distributed in the code repository.

## Ablations

AWS reference implementations are under `experiments/ablations/`. They preserve
original experiment logic and source paths; they are not a portable deployment
installer. Some load frozen source batches or recordings that will accompany the
resource release.

- **Starting distance:** near starts use approximately one third of the original
  navigable route distance and preserve orientation.
- **Budget:** VLM uses 20/40/60 actions; VLA uses 30/60/90 simulated seconds.
- **Guidance:** distinguish removing examples while keeping the type hint from
  removing both. Use the preserved ablation launchers; the base `--no-icl` flag
  alone does not reproduce every guidance setting.
- **Multiple anomalies:** the preprint uses 21 anchors and two randomized
  configurations for each two- and three-anomaly condition: 42 runs per condition.
  `section62-gemini-random-types-20260924` is the final random-composition driver;
  `gemini-unreal-multibug-20260922` holds the earlier construction/QA helpers.

## Validation limits

Offline tests verify software contracts with synthetic environments. They do not
verify rendering, navigation, model access, or paper scores. See
[validation.md](validation.md) for exact outcomes, including inherited service-test
failures and missing-resource skips.
