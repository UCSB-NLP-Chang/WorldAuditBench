# Commands

| Command | Purpose |
|---|---|
| `experiments/run.py --agent gemini --tasks S01 --download` | Run an agent on one or more tasks |
| `view_task.py S01 --download` | View and explore a task |
| `download_dataset.py` | Download task data and shared examples |
| `download_resources.py --package subway` | Download an environment |
| `serve_unreal.py --task S01` | Start an Unreal environment endpoint |
| `check_release.py` | Check task and package coverage |

Use `python <command> --help` for options. Run commands from the repository root.
`experiments/agents.json` contains the model presets. The export and package-check
scripts support maintaining the Hugging Face release.
