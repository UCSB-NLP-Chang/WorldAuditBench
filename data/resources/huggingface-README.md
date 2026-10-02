---
pretty_name: WorldAuditBench
task_categories:
- other
language:
- en
size_categories:
- n<1K
tags:
- worldauditbench
- 3d
- simulation
- benchmark
- multimodal
configs:
- config_name: default
  data_files:
  - split: test
    path: dataset/tasks.parquet
---

# WorldAuditBench

**Interactive 3D World Auditing with Multimodal Agents**

[![Paper](https://img.shields.io/badge/Paper-arXiv-B31B1B?style=flat-square)](https://arxiv.org/pdf/2609.40325) [![Code](https://img.shields.io/badge/Code-GitHub-24292F?style=flat-square)](https://github.com/UCSB-NLP-Chang/WorldAuditBench) [![Project page](https://img.shields.io/badge/Project-Website-2563EB?style=flat-square)](https://ucsb-nlp-chang.github.io/WorldAuditBench/) [![Demo Space](https://img.shields.io/badge/Demo-Hugging_Face-F9AB00?style=flat-square)](https://huggingface.co/spaces/ziyjiang/WorldAuditBench)

213 tasks · 13 environments · 5 anomaly families  
UC Santa Barbara · MIT CSAIL · MIT–IBM Watson AI Lab

WorldAuditBench evaluates whether multimodal agents can **explore a 3D world, investigate suspicious observations, and identify anomalies with visual evidence**. An agent may need to approach an object, test a collision, change its viewpoint, or revisit a location to establish what is wrong.

![Examples of the five anomaly families in WorldAuditBench](https://raw.githubusercontent.com/UCSB-NLP-Chang/WorldAuditBench/main/docs/figures/anomaly-taxonomy.webp)

*Representative examples from the paper: static physics, interactive physics, spatial consistency, temporal consistency, and semantic consistency.*

## The benchmark

The evaluation set spans **126 Unreal Engine tasks** and **87 Three.js tasks**, covering furnished interiors, urban scenes and natural environments.

| Anomaly family | What agents investigate | Tasks |
| --- | --- | ---: |
| Static physics | Floating objects, intersections and implausible scale | 59 |
| Interactive physics | Missing collisions, unexpected obstacles and abnormal trajectories | 41 |
| Spatial consistency | Visibility, viewpoint, lighting and material inconsistencies | 51 |
| Temporal consistency | Changes in existence, attributes or operational state | 40 |
| Semantic consistency | Improper configurations and historical incompatibilities | 22 |
| **Total** | **15 anomaly types across 13 environments** | **213** |

**Unreal:** Ancient City, Indoor, Industrial, Medieval Village, Rural Australia, Subway and Urban.

**Three.js:** Airfield, Cottage, House, Reef, Sponza and Wilderness.

## Data

**One task per row.** [`dataset/tasks.parquet`](https://huggingface.co/datasets/ziyjiang/WorldAuditBench/tree/main/dataset) contains all 213 tasks, including inputs, categories, rubrics and maps.

| Field | Contents |
| --- | --- |
| `task_id`, `engine`, `environment` | Task and environment identifiers |
| `category`, `subcategory` | Anomaly family and type |
| `input` | Instruction and scene description |
| `rubric` | `anomaly`: anomaly description; `expected`: expected behavior |
| `map` | Map path or scene URL |

[In-context examples](https://huggingface.co/datasets/ziyjiang/WorldAuditBench/tree/main/examples) are grouped by subcategory.

```python
from datasets import load_dataset

benchmark = load_dataset("ziyjiang/WorldAuditBench", split="test")
task = benchmark[0]
print(task["task_id"], task["input"])
```

## Auditing paradigms

![VLM agents and VLA exploration followed by VLM analysis](https://raw.githubusercontent.com/UCSB-NLP-Chang/WorldAuditBench/main/docs/figures/auditing-paradigms.webp)

**VLM agents** reason during exploration and choose their next actions from observations and evidence, with a budget of 40 actions. **VLA + VLM** separates exploration from analysis: a VLA explores for 60 simulated seconds, then a VLM examines the recorded trajectory.

The strongest evaluated agent reaches **42.3%** success, compared with **83.4%** for humans.

## Citation

```bibtex
@article{jiang2026worldauditbench,
  title={WorldAuditBench: Interactive 3D World Auditing with Multimodal Agents},
  author={Jiang, Ziyan and Yang, Jingbo and Ji, Jiabao and Liu, Yujian and Wu, Qiucheng and Jaakkola, Tommi and Zhang, Yang and Chang, Shiyu},
  journal={arXiv preprint arXiv:2609.40325},
  year={2026}
}
```
