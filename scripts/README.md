# Running WorldAuditBench

Start with the [paper reproduction guide](../docs/reproduction.md). Run commands
from the repository root.

| Entry point | Purpose |
| --- | --- |
| [`download_dataset.py`](download_dataset.py) | Download the unified task table and shared ICL examples |
| [`download_resources.py`](download_resources.py) | Download verified environment packages and images; generate local profiles |
| [`serve_unreal.py`](serve_unreal.py) | Start one installed Unreal task on a Linux GPU host |
| [`agent/vlm/native/setup.py`](../agent/vlm/native/setup.py) | Install the native-client Python runtime |
| [`agent/vlm/native/launch.py`](../agent/vlm/native/launch.py) | Run one VLM auditing episode |
| [`scripts/experiments/run_batch.py`](experiments/run_batch.py) | Run a batch of auditing episodes |
| [`agent/vla/replay.py`](../agent/vla/replay.py) | Analyze and judge VLA recordings |
| [`check_release.py`](check_release.py) | Check task splits and environment package coverage |
| [`run_vla_threejs.sh`](run_vla_threejs.sh), [`run_vla_ue.sh`](run_vla_ue.sh) | Original VLA collection wrappers; configure local resources and cache paths before use |

`run_agent.sh` launches the tool-calling agent described in [`agent/vlm/README.md`](../agent/vlm/README.md).
`check_gpu.sh`, `fetch_assets.sh`, `gpu_wait.py`, and `serve_model*.sh` support that
workflow. The model-serving scripts retain the original machine's vLLM and cache
paths; adapt these before running them on another host.

[`vla-lists/`](vla-lists) contains collection lists. The paper evaluation split
is defined by [`data/benchmark/splits/`](../data/benchmark/splits).
