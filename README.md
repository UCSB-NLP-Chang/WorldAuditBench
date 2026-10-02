<div align="center">

<h1><img src="docs/figures/logo.png" width="42" alt=""> WorldAuditBench</h1>
<h3>Interactive 3D World Auditing with Multimodal Agents</h3>

<p>
  <a href="https://xmhzz2018.github.io/">Ziyan Jiang</a><sup>1,*</sup> ·
  <a href="https://kimperyang.github.io/">Jingbo Yang</a><sup>1,*</sup> ·
  <a href="https://question406.github.io/">Jiabao Ji</a><sup>1,*</sup> ·
  <a href="https://yujianll.github.io/">Yujian Liu</a><sup>1</sup><br>
  <a href="https://wuqiuche.github.io/">Qiucheng Wu</a><sup>1</sup> ·
  <a href="https://people.csail.mit.edu/tommi/">Tommi Jaakkola</a><sup>2</sup> ·
  <a href="https://mitibm.mit.edu/people/yang-zhang/">Yang Zhang</a><sup>3</sup> ·
  <a href="https://code-terminator.github.io/">Shiyu Chang</a><sup>1</sup>
</p>
<p><sup>1</sup> UC Santa Barbara &nbsp; <sup>2</sup> MIT CSAIL &nbsp; <sup>3</sup> MIT-IBM Watson AI Lab<br><sup>*</sup> Equal contribution</p>

<p>
  <a href="https://arxiv.org/abs/2609.40325"><img src="docs/figures/paper-badge.svg" alt="Paper on arXiv"></a>
  <a href="https://ucsb-nlp-chang.github.io/WorldAuditBench/"><img src="docs/figures/project-badge.svg" alt="Project page"></a>
  <a href="https://huggingface.co/datasets/ziyjiang/WorldAuditBench"><img src="docs/figures/dataset-badge.svg" alt="Dataset on Hugging Face"></a>
  <a href="https://ucsb-nlp-chang.github.io/WorldAuditBench/#explore"><img src="docs/figures/demo-badge.svg" alt="Explore demos"></a>
</p>

**213 tasks · 13 environments · 5 anomaly families · 2 auditing paradigms**

</div>

WorldAuditBench evaluates whether multimodal agents can **explore a 3D world, investigate suspicious observations, and identify anomalies with visual evidence**. It covers both Unreal Engine 5 and Three.js environments, from furnished interiors to cities and open landscapes.

**[Demonstrations](#demonstrations)** · **[Benchmark](#benchmark)** · **[Quick start](#quick-start)** · **[Evaluation](#evaluation)** · **[Resources](#resources)** · **[Citation](#citation)**

## Demonstrations

[![Representative examples of the five anomaly families in WorldAuditBench, from the paper.](docs/figures/anomaly-taxonomy.webp)](https://ucsb-nlp-chang.github.io/WorldAuditBench/#explore)

*Representative cases from the paper, covering static physics, interactive physics, spatial consistency, temporal consistency, and semantic consistency.*

Watch the recorded demonstrations and explore all **15 anomaly types** on the [project page](https://ucsb-nlp-chang.github.io/WorldAuditBench/#explore).

## Benchmark

Auditing requires more than recognizing an unusual image. An agent may need to approach an object, test a collision, change its viewpoint, or revisit a location to establish what is wrong.

| Anomaly family | Examples | Tasks |
| --- | --- | ---: |
| Static physics | Floating objects, intersections, implausible scale | 59 |
| Interactive physics | Missing or unexpected collisions, abnormal trajectories | 41 |
| Spatial consistency | Visibility, viewpoint, lighting, and material inconsistencies | 51 |
| Temporal consistency | Changes in existence, attributes, or operational state | 40 |
| Semantic consistency | Improper configurations and historical incompatibilities | 22 |
| **Total** | **126 Unreal Engine 5 + 87 Three.js tasks** | **213** |

The paper compares two auditing paradigms:

- **VLM agents:** reason during exploration and choose their next actions using observations and evidence memory, with a budget of **40 actions**.
- **VLA + VLM:** a VLA explores for **60 simulated seconds**, then a VLM analyzes the recorded trajectory.

<p align="center">
  <img src="docs/figures/auditing-paradigms.webp" width="100%" alt="The two auditing paradigms: VLM reasoning during exploration, and VLA exploration followed by VLM analysis.">
</p>

The strongest evaluated agent reaches **42.3%** success, compared with **83.4%** for humans. See the [interactive results](https://ucsb-nlp-chang.github.io/WorldAuditBench/#results) and [paper](https://arxiv.org/pdf/2609.40325) for the full comparison.

## Quick start

### 1. Install

Use **Python 3.11+** on Linux or macOS for the Python tools. Running Unreal environments requires a configured Linux GPU host and the environment packages listed under [Resources](#resources).

```bash
git clone https://github.com/UCSB-NLP-Chang/WorldAuditBench.git
cd WorldAuditBench

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Explore the evaluation set

The [Hugging Face dataset](https://huggingface.co/datasets/ziyjiang/WorldAuditBench) contains one row per task: public inputs, categories, English rubrics and map identifiers. Shared in-context examples are stored once in `examples/`.

```bash
python scripts/download_dataset.py
```

```python
from auditor.task_dataset import load_task

task = load_task("S01")
print(task["input"])
print(task["rubric"]["en"])
```

See the [task data guide](docs/task-data.md) for the schema and input/evaluation boundary. The download is pinned by revision and checksum; subsequent runs reuse the local cache.

### 3. Set up an auditor

The paper's VLM auditors run through native model clients and a shared MCP tool interface. Prepare their Python runtime:

```bash
python scripts/native-agents/setup.py
python scripts/native-agents/launch.py --help
```

Install and authenticate the native client you plan to use: Codex, Claude Code, Gemini CLI, OpenCode, or Qwen Code. See the [native-agent guide](docs/native-agent-mcp.md) for configuration and the [reproduction guide](docs/reproduction.md) for exact model and reasoning settings.

Download a compiled environment and the demonstration images, then start its local service on a Linux GPU host:

```bash
python scripts/download_resources.py --package subway
python scripts/serve_unreal.py --task S03 --gpu 0 --port 19100
```

In a second terminal, run an auditing episode:

```bash
python scripts/native-agents/launch.py gemini \
  --environment unreal-http --env-url http://127.0.0.1:19100 \
  --task S03 --model gemini-3.8-flash --gemini-thinking medium \
  --max-actions 40 --max-tool-calls 400 --require-full-budget \
  --observation on-demand --run-dir out/runs/gemini-S03
```

For Three.js configuration, VLA exploration, trajectory replay, and ablations, follow the [reproduction guide](docs/reproduction.md).

## Evaluation

Agents submit anomaly reports with supporting visual evidence. The judge evaluates each report against the task rubric and returns a binary success score with an explanation. The paper reports success over the fixed **213-task** evaluation set.

| Workflow | Code / documentation |
| --- | --- |
| Interactive VLM auditing | [`scripts/native-agents/launch.py`](scripts/native-agents/launch.py) · [MCP tools](docs/native-agent-mcp.md) |
| VLA exploration | [`harness/vla_ue.py`](harness/vla_ue.py) · [`harness/vla_explore.py`](harness/vla_explore.py) |
| Analysis of VLA trajectories | [`scripts/native-agents/run_vla_replay.py`](scripts/native-agents/run_vla_replay.py) |
| Report judging | [`eval/judge.py`](eval/judge.py) · [Judge protocol](docs/binary-judge.md) |
| Ablation experiments | [`experiments/ablations/`](experiments/ablations/) · [Protocol settings](docs/reproduction.md#ablations) |

## Resources

Code and reproducibility records are available here. The unified task dataset, shared demonstrations and compiled environments are distributed on [Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench).

| Resource | Availability |
| --- | --- |
| Task inputs and evaluation rubrics | [Hugging Face dataset](https://huggingface.co/datasets/ziyjiang/WorldAuditBench/tree/main/dataset) |
| Auditing agents, evaluation, and environment source | Available in this repository |
| Demonstration videos | [Project page](https://ucsb-nlp-chang.github.io/WorldAuditBench/#explore) |
| Compiled Unreal and Three.js environments | [Download and run](docs/resources.md) |
| In-context demonstration images | [Available on Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench) |
| Interactive five-family demo | [Hugging Face Space](https://huggingface.co/spaces/ziyjiang/WorldAuditBench) · requires running GPU hardware |
| VLA trajectories and frozen ablation inputs | Pending |
| Open-P2P model setup and checkpoint instructions | Coming soon |

See [resource details](docs/resources.md) for the files required to run the benchmark. Third-party environments and models retain their respective licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).

## Repository structure

Start with the [documentation](docs/README.md) and [script entry points](scripts/README.md).
The [repository map](docs/repository-layout.md) explains how the components fit together.

```text
benchmark/              Task definitions, scene descriptions, and evaluation splits
examples/icl/           In-context demonstrations and evaluation exclusions
scripts/native-agents/  Native model clients and experiment launchers
auditor/mcp_agent/      Shared auditing tools and environment connections
agent/                  Tool-calling VLM agent and evidence memory
harness/                VLA exploration and environment runners
eval/                   Report judges and evaluation utilities
candidate_environments/ Three.js environment source
env/                    Browser runtime and anomaly configurations
unreal/                 Unreal source, plugins, and runtime policies
experiments/ablations/   Ablation implementations
services/               Human exploration, review, and evaluation interfaces
resources/              Pinned runtime downloads and resource manifests
docs/                   Setup, protocols, and resource documentation
```

Earlier pilots and reruns are archived in [`scripts/legacy/`](scripts/legacy/);
development plans and handoffs are in [`docs/history/`](docs/history/).

### Development checks

```bash
python -m pip install -r requirements-dev.txt
python scripts/check_release.py
python -m pytest -q -m 'not chromium and not live'
```

These checks cover code and interfaces; they do not launch the full benchmark. See [validation details](docs/validation.md) for resource-dependent checks.

## Citation

```bibtex
@misc{jiang2026worldauditbench,
  title  = {WorldAuditBench: Interactive 3D World Auditing
            with Multimodal Agents},
  author = {Ziyan Jiang and Jingbo Yang and Jiabao Ji and
            Yujian Liu and Qiucheng Wu and Tommi Jaakkola and
            Yang Zhang and Shiyu Chang},
  year   = {2026},
  eprint = {2609.40325},
  archivePrefix = {arXiv},
  primaryClass = {cs.AI},
  url    = {https://arxiv.org/abs/2609.40325}
}
```

For questions or bug reports, please [open an issue](https://github.com/UCSB-NLP-Chang/WorldAuditBench/issues).
