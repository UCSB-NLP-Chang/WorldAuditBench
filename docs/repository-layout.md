# Repository structure

| Directory | Contents |
| --- | --- |
| `agent/`, `auditor/` | Auditing agents, MCP tools and evidence storage |
| `benchmark/` | Task definitions, evaluation splits and environment policies |
| `examples/` | In-context example metadata |
| `scripts/`, `harness/` | Setup, launchers and VLA exploration |
| `eval/`, `experiments/` | Scoring and ablations |
| `env/`, `candidate_environments/` | Three.js runtime and scene builders |
| `unreal/` | Unreal plugins and build tools |
| `services/` | Human exploration, review and evaluation interfaces |
| `spaces/` | Hugging Face demo application |
| `resources/` | Dataset and environment download manifests |
| `tools/` | Environment conversion and inspection utilities |
| `tests/` | Automated tests |
| `docs/` | Usage guides and paper figures |

Task data, examples and compiled environments are hosted on
[Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench).
The project website is maintained on the `gh-pages` branch.
