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
  <a href="https://arxiv.org/pdf/2609.40325"><img src="docs/figures/paper-badge.svg" alt="Paper on arXiv"></a>
  <a href="https://ucsb-nlp-chang.github.io/WorldAuditBench/"><img src="docs/figures/project-badge.svg" alt="Project page"></a>
  <a href="https://huggingface.co/datasets/ziyjiang/WorldAuditBench"><img src="docs/figures/dataset-badge.svg" alt="Dataset on Hugging Face"></a>
  <a href="https://huggingface.co/spaces/ziyjiang/WorldAuditBench"><img src="docs/figures/demo-badge.svg" alt="Demo on Hugging Face"></a>
</p>

**213 tasks · 13 environments · 5 anomaly families · 2 auditing paradigms**

</div>

WorldAuditBench evaluates whether multimodal agents can **explore a 3D world, investigate suspicious observations, and identify anomalies with visual evidence**. It covers both Unreal Engine 5 and Three.js environments, from furnished interiors to cities and open landscapes.

**[Demonstrations](#demonstrations)** · **[Benchmark](#benchmark)** · **[Quick start](#quick-start)** · **[Resources](#resources)** · **[Citation](#citation)**

## Demonstrations

[![Representative examples of the five anomaly families in WorldAuditBench, from the paper.](docs/figures/anomaly-taxonomy.webp)](https://ucsb-nlp-chang.github.io/WorldAuditBench/#explore)

*Representative cases from the paper, covering static physics, interactive physics, spatial consistency, temporal consistency, and semantic consistency.*

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

The strongest evaluated agent reaches **42.3%** success, compared with **83.4%** for humans.

## Quick start

Python 3.11+. Unreal environments require Linux and an NVIDIA GPU.
Three.js environments run in Chromium on Linux or macOS.

```bash
git clone https://github.com/UCSB-NLP-Chang/WorldAuditBench.git
cd WorldAuditBench
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python agent/vlm/native/setup.py
```

Install and authenticate the model client you want to use: Codex, Claude Code,
Gemini CLI, Qwen Code or OpenCode. See the [agent guide](docs/native-agent-mcp.md).

### Run an agent

```bash
python scripts/experiments/run.py --agent gemini --tasks S01 --download
```

Use `codex`, `claude`, `gemini`, `qwen` or `muse` for `--agent`.
Model IDs and reasoning settings are in
[`agents.json`](scripts/experiments/agents.json). `--download` installs the selected
environment from Hugging Face; existing verified downloads are reused.

```bash
# Three.js task
python scripts/experiments/run.py --agent codex --tasks JS_AF01 --download

# A batch of tasks
python scripts/experiments/run.py --agent gemini \
  --tasks @data/benchmark/splits/unreal.txt --download --output out/gemini-unreal

# Budget and example settings
python scripts/experiments/run.py --agent claude --tasks S01 \
  --max-actions 20 --no-icl --output out/claude-20-noicl
```

Each task produces `report.json`, `evidence.json` and its recording under the
output directory. `--dry-run` prints the commands without running an environment
or calling a model. Additional client options can be passed after `--`.

### Run the judge

```bash
python -m judge.judge --task S01 \
  --model-output out/runs/gemini/S01/report.json \
  --evidence out/runs/gemini/S01/evidence.json \
  --output out/runs/gemini/S01/judge.json
```

The judge loads the task rubric and returns `score` (0 or 1) and `reason`.
It uses GPT-6 Astra with medium reasoning through an authenticated Codex CLI.
See [judge options](docs/binary-judge.md).

### View a task

```bash
python scripts/view_task.py --download
# Or preselect a task:
python scripts/view_task.py JS_AF01 --download
```

The command opens a task browser with environment and taxonomy filters, input
prompts, rubrics and interactive exploration. Use `--no-browser` on a remote host
and forward the printed loopback port to your local browser.

### VLA exploration

Open-P2P records exploration, then a VLM analyzes the recording.
See [VLA setup and commands](docs/reproduction.md#vla-exploration).

## Resources

[Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench) hosts the
213-task table, shared in-context examples and compiled environments.
[Task schema](docs/task-data.md) · [Download options](docs/resources.md)

## Repository structure

```text
agent/vlm/             VLM clients and auditing tools
agent/vla/             VLA exploration and recording analysis
judge/                 GPT-6 judge and prompt
scripts/experiments/    Agent presets and experiment launcher
scripts/view_task.py    Interactive task viewer
scripts/               Downloads and environment launchers
environments/          Environment connections
data/                  Dataset loading and release manifests
tests/                 Automated checks
```

```bash
pip install -r requirements-dev.txt
python scripts/check_release.py
python -m pytest -q
```

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
