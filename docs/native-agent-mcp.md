# Run VLM agents

The model's native client controls reasoning and tool calls. The MCP server
provides movement, observation, evidence inspection, notes and anomaly reporting.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
python agent/vlm/native/setup.py
```

Install and authenticate the client used by your experiment:

| Preset | Client |
|---|---|
| `codex` | Codex CLI |
| `claude` | Claude Code |
| `gemini` | Gemini CLI |
| `qwen` | Qwen Code |
| `muse` | OpenCode with the OpenRouter provider |

Use the client's own authentication flow. API keys remain in the local client
configuration or environment. The launcher also supports client-specific key-file
options; `python agent/vlm/native/launch.py --help` lists them.

## Experiments

```bash
python scripts/experiments/run.py --agent gemini --tasks S01 --download
python scripts/experiments/run.py --agent codex --tasks JS_AF01 --download
```

`--tasks` accepts comma-separated IDs or `@path/to/split.txt`.
The presets in `scripts/experiments/agents.json` record the paper's model IDs
and reasoning settings. `--model` overrides the model ID. Client availability
and authentication must be configured on the machine running the experiment.

Defaults are 40 actions, matching in-context examples and on-demand observations.
Use `--max-actions` and `--no-icl` to change these settings. Choose a fresh
`--output` directory for each experiment; existing task attempts are not overwritten.

Pass extra native-client options after `--`, for example:

```bash
python scripts/experiments/run.py --agent gemini --tasks S01 -- \
  --gemini-auth gemini-api-key
```

`--dry-run` prints the launch commands without downloading environments or calling
a model. Actual runs write each task's final `report.json`, cited `evidence.json`,
frames and native-client logs into the output directory.

## Individual launchers

For an environment server you already started:

```bash
python scripts/serve_unreal.py --task S01 --port 19100
python agent/vlm/native/launch.py gemini --task S01 \
  --environment unreal-http --env-url http://127.0.0.1:19100 \
  --max-actions 40 --require-full-budget --run-dir out/individual-S01
```

The task input and shared example are loaded from the pinned Hugging Face dataset.
Rubrics are loaded by the judge only.
