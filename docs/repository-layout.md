# Repository layout

- `agent/vlm/`: VLM clients, MCP tools and evidence handling.
- `agent/vla/`: exploration and recorded-trajectory analysis.
- `judge/`: the formal GPT-6 judge and its prompt.
- `scripts/experiments/`: agent presets and experiment commands.
- `scripts/view_task.py`: interactive task viewing.
- `environments/`: environment connections.
- `data/`: dataset loading, task definitions, evaluation splits and pinned download manifests.
- `tests/`: automated checks.

Task data, examples and compiled environments are hosted on
[Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench).

Internal repair patches, deployment snapshots, validation logs and screenshots
are kept in the private AWS archive. Generated local outputs belong under `out/`
or `runs/` and are excluded from version control.
