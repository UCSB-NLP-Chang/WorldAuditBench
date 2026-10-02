# Task data

The public data lives in **[WorldAuditBench on Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench)**.

```text
dataset/tasks.parquet       One row per task: inputs, categories, rubrics and identifiers
examples/icl-examples.tar.gz Shared demonstration text and 29 images, stored once
unreal/                    Compiled Unreal environments, one archive per environment
three.js/                  Built Three.js environments, one archive per environment
```

The task table, shared examples and compiled environments are available. See the
[resource guide](resources.md) for installation commands and release coverage.

## Load the data

```python
from datasets import load_dataset

tasks = load_dataset("ziyjiang/WorldAuditBench", split="test")
task = next(t for t in tasks if t["task_id"] == "S01")
print(task["input"])
print(task["rubric"])
```

The **213 rows** cover **126 Unreal and 87 Three.js tasks**, across 13 environments.

| Field | Meaning |
| --- | --- |
| `task_id`, `engine`, `environment` | Stable task ID and environment |
| `category`, `subcategory` | Anomaly family and type |
| `input` | Instruction and scene description |
| `rubric` | `anomaly`: anomaly description; `expected`: expected behavior |
| `map` | Map path or scene URL used to load this task |

The category and subcategory are stored only at the top level. The launcher
uses them to supply the assigned type; the input does not repeat them or ask
the model to classify its report. Tool instructions specify how to finish an episode.

In-context demonstrations are shared. The `subcategory` selects the matching
example in `examples/`; their text and image bytes are not duplicated in task
rows or environment packages. The archive includes `context.json`, an evaluation
exclusion list and an `images/` directory beneath `icl/`.

## Use the GitHub runners

```bash
python scripts/download_dataset.py
```

This downloads and verifies the versions pinned in `data/resources/dataset.json`.
The cache lives under `out/dataset/`. Downloads are reused across tasks.

The native launcher reads this task table by default and loads the shared
example for the assigned subcategory. Supply `--dataset /path/tasks.parquet` for
a local table. `--no-icl` selects the zero-shot ablation.

```bash
python -m judge.judge --task S01 --model-output agent_output.json
```

The judge obtains S01's English rubric from the table and uses the shared
English instructions in `judge/judge_prompt.md`. Custom rubric files remain
supported through `--rubrics`. Version pins and checksums live in GitHub's
`data/resources/` configuration, outside the public task table.

The model receives only the public input fields, the selected demonstration,
tool instructions, budgets and observations during exploration. The launcher
saves its assembled initial prompt as `<run-dir>/prompt.txt`. **Rubrics are evaluation answers and are never included in model input.**

The public rubric contains only `anomaly` and `expected`. Reproduction routes
are omitted; conditions necessary to identify a dynamic anomaly remain in
`anomaly`. This is a simplified format for new runs. Published experiment
records retain their original prompts and rubrics (including reproduction
steps); the reported paper scores have not been recomputed with this format.

## Updating task descriptions

`agent/vlm/native/task-scenes.json` is the shared description source. Tasks in the
same scene use one description of the scene and its accessible areas, independent
of their starting positions. `data/benchmark/paper-tasks.json` contains the task
identifiers, categories, launch metadata and authored rubrics used by
`scripts/export_hf_dataset.py`.

After editing descriptions, export and publish `dataset/tasks.parquet` to Hugging
Face, then update its commit, size and SHA-256 in `data/resources/dataset.json`.
The launchers and viewer use this pinned table by default. `--dataset` selects a
local table for validation before publication.
