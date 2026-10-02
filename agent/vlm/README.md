# VLM auditing

`native/launch.py` starts a native model client for an auditing episode.
`mcp/` provides environment actions, evidence frames and reporting tools.
The shared modules handle frame storage, anomaly reports and exploration state.

```bash
python agent/vlm/native/setup.py
python agent/vlm/native/launch.py --help
```

Use the [agent guide](../../docs/native-agent-mcp.md) for model clients and
[reproduction guide](../../docs/reproduction.md) for experiment settings.

## Scoring

```bash
python -m judge.judge --task S01 --model-output report.json \
  --images evidence.png --output result.json
```

Task inputs, rubrics and in-context examples are loaded from the pinned
[Hugging Face dataset](https://huggingface.co/datasets/ziyjiang/WorldAuditBench).
