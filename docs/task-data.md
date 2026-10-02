# Task data

The public data lives in **[WorldAuditBench on Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench)**.

```text
dataset/tasks.parquet       One row per task: inputs, categories, rubrics and identifiers
examples/icl-examples.tar.gz Shared demonstration text and 29 images, stored once
unreal/                    Compiled Unreal environments, one archive per environment
three.js/                  Built Three.js environments, one archive per environment
```

The task table and shared examples are available now. Environment archives are
being migrated to the last two directories; see the [resource guide](resources.md)
for currently supported installation commands and validation status.

## Load the data

```python
from datasets import load_dataset

tasks = load_dataset("ziyjiang/WorldAuditBench", split="test")
task = next(t for t in tasks if t["task_id"] == "S01")
print(task["input"])
print(task["rubric"]["en"])
```

The **213 rows** cover **126 Unreal and 87 Three.js tasks**, across 13 environments.

| Field | Meaning |
| --- | --- |
| `task_id`, `engine`, `environment` | Stable task ID and environment |
| `category`, `subcategory` | Anomaly family and type |
| `input` | Auditing instruction, public scene description and assigned subcategory |
| `rubric` | English and Chinese expected behavior, reproduction steps and acceptance criteria; also the original rubric text |
| `runtime` | Map, source case and task revision |
| `provenance` | Source revision and reference hashes, including the selected ICL demonstration hash |
| `judge_prompt` | Instructions for evaluating the final report |

In-context demonstrations are shared. The `subcategory` selects the matching
example in `examples/`; their text and image bytes are not duplicated in task
rows or environment packages. The archive includes `context.json`, an evaluation
exclusion list and an `images/` directory beneath `icl/`.

## Use the GitHub runners

```bash
python scripts/download_dataset.py
```

This downloads and verifies the versions pinned in `resources/dataset.json`.
The cache lives under `out/dataset/`. Downloads are reused across tasks.

The native launcher reads this task table by default and loads the shared
example for the assigned subcategory. Supply `--dataset /path/tasks.parquet` for
a local table. `--no-icl` selects the zero-shot ablation.

```bash
python -m eval.judge --task S01 --model-output agent_output.json
```

The judge obtains S01's rubric and judge prompt from the same table. Custom
rubric files remain supported through `--rubrics`.

The model receives only the public input fields, the selected demonstration,
tool instructions, budgets and observations during exploration. The launcher
saves its assembled initial prompt as `<run-dir>/prompt.txt`. **Rubrics and
reproduction steps are evaluation answers, not model input.**

## Source records and archival experiments

The JSON catalogs in GitHub preserve the authored task definitions and earlier
experiment records. `scripts/export_hf_dataset.py` builds the public task table
from those sources. Regular benchmark runs use the pinned HF table; pass
`--legacy-task-files` to the native or VLA replay launcher only when reproducing
archival tasks outside the paper evaluation split.
