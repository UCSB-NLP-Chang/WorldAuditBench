# Repository map

`main` contains the benchmark code. `gh-pages` contains the
[project website](https://ucsb-nlp-chang.github.io/WorldAuditBench/), its figures,
videos, and paper PDF. Large runtime resources are pending Hugging Face release.

## Data and examples

| Directory | Contents |
| --- | --- |
| [`benchmark/`](../benchmark/) | Paper task definitions, evaluation splits, scene descriptions, and runtime policies |
| [`examples/icl/`](../examples/icl/) | Demonstration text and evaluation exclusions; images pending |
| [`resources/`](../resources/) | Restore paths, resource hashes, and release status |

Use `benchmark/paper-tasks.json` and `benchmark/splits/` for the **213 paper tasks**.
The larger `benchmark/tasks.json` and `services/review/tasks.json` catalogs belong
to review workflows and include other entries.

## Agents and evaluation

| Directory | Contents |
| --- | --- |
| [`scripts/native-agents/`](../scripts/native-agents/) | Native model-client launchers and batch orchestration |
| [`auditor/mcp_agent/`](../auditor/mcp_agent/) | MCP tool server, environment connections, and example delivery |
| [`agent/`](../agent/) | Tool-calling VLM agent, observations, evidence memory, and tests |
| [`harness/`](../harness/) | Environment runners and VLA exploration |
| [`eval/`](../eval/) | Report judges and trajectory evaluation |
| [`experiments/ablations/`](../experiments/ablations/) | Paper ablation drivers and configurations |
| [`tests/`](../tests/) | Native-agent and protocol tests |

`agent/` and `auditor/` implement different layers: the former contains the
tool-calling agent; the latter exposes auditing tools to native model clients.
The dated ablation folders identify the captured experiment variants.

## Environments and services

| Directory | Contents |
| --- | --- |
| [`candidate_environments/src/`](../candidate_environments/src/) | Three.js environment builders and attributed upstream scene source |
| [`env/`](../env/) | Browser environment runtime, anomaly configurations, and human/agent pages |
| [`unreal/`](../unreal/) | Unreal plugins, recovered authoring source, runtime patches, and deployed bridge |
| [`services/`](../services/) | Human exploration, review, and evaluation services |
| [`tools/`](../tools/) | Environment generation, conversion, and inspection utilities |

The Three.js runtime and builders use their existing directory names in page URLs
and build scripts. The Unreal `source-snapshot/` tree preserves multiple project
workspaces; repeated plugin files belong to those project snapshots. Explore and
Evaluate also contain separate deployed versions of the `bf` package. These
copies should be compared in their project context before being consolidated.

## Historical material and local output

- `scripts/legacy/`: 53 earlier pilots, reruns, scheduling scripts, and summary helpers.
- `docs/history/`: earlier development plans and experiment handoffs.
- `docs/migration/`: the import record and source checksums.
- `out/`, `output/`, `runs/`, `.venv/`, and caches: ignored local output or dependencies.

The historical material retains original paths and assumptions. Follow the
[reproduction guide](reproduction.md) for current public checkout instructions.
