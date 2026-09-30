# WorldAuditBench

Code for **WorldAuditBench: Interactive 3D World Auditing With Multimodal Agents**.

WorldAuditBench evaluates whether multimodal agents can explore interactive 3D
worlds and identify anomalies from visual evidence. The paper evaluates **213
tasks across 13 environments**: 126 tasks in Unreal Engine 5 and 87 in Three.js.

- **`main`**: benchmark definitions, auditing agents, evaluation, and environment source.
- **[`gh-pages`](https://github.com/UCSB-NLP-Chang/WorldAuditBench/tree/gh-pages)**: project page and demonstration videos.
- **Resources**: packaged environments, editable scene assets, model weights, and
  recording/example images are **pending a Hugging Face release**. See
  [resource status](docs/resources.md). Source checks can run before those downloads.

## Setup

Use Python 3.11+ on Linux or macOS. Unreal execution requires a configured Linux
GPU host and the external runtime packages; it is not part of the source-only setup.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/check_release.py
python -m pytest -q -m 'not chromium and not live'
```

Native model clients use a dedicated runtime:

```bash
python scripts/native-agents/setup.py
python scripts/native-agents/launch.py --help
```

Install and authenticate the native CLI for the model you use. The repository
includes the shared MCP tools and agent implementation; setup does not require
cloning a separate private code repository.

## Paper experiments

| Component | Entry point |
|---|---|
| Exact 213-task evaluation set | [`benchmark/paper-tasks.json`](benchmark/paper-tasks.json), [`benchmark/splits/`](benchmark/splits/) |
| VLM auditors: Codex, Claude Code, Gemini CLI, OpenCode, Qwen Code | [`scripts/native-agents/launch.py`](scripts/native-agents/launch.py) |
| Shared auditing tools and evidence memory | [`auditor/mcp_agent/`](auditor/mcp_agent/), [`agent/`](agent/) |
| VLA exploration: Open-P2P | [`harness/vla_ue.py`](harness/vla_ue.py), [`harness/vla_explore.py`](harness/vla_explore.py) |
| VLM analysis of recorded VLA trajectories | [`scripts/native-agents/run_vla_replay.py`](scripts/native-agents/run_vla_replay.py) |
| Binary report judge | [`eval/judge.py`](eval/judge.py), [`eval/judge_prompt.md`](eval/judge_prompt.md) |
| Distance, budget, guidance, and multiple-anomaly ablations | [`experiments/ablations/`](experiments/ablations/) |
| Three.js environment source | [`candidate_environments/src/`](candidate_environments/src/), [`env/`](env/) |
| Unreal source, plugins, runtime policies | [`unreal/`](unreal/) |
| Human review, exploration, and evaluation services | [`services/`](services/) |

See [reproduction instructions](docs/reproduction.md) for protocol settings and
[validation status](docs/validation.md) for the checks performed during migration.
The online review catalog includes baselines and other administrative entries;
use the paper split for reported results.

## Source and resources

The code was collected from the active AWS deployment and experiment workspaces
and checked against the arXiv manuscript on 2026-09-30. Source origins and file
hashes are recorded in [the migration receipt](docs/migration/README.md).
Unreal editor assets and runtime packages are distributed separately; recovered
source snapshots alone do not reconstruct every published binary.

Third-party environment code retains its source attribution and license files.
See [third-party sources](THIRD_PARTY.md) before redistributing environment assets.
