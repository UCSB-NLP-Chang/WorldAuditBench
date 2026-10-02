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

This downloads and verifies the versions pinned in `resources/dataset.json`.
The cache lives under `out/dataset/`. Downloads are reused across tasks.

The native launcher reads this task table by default and loads the shared
example for the assigned subcategory. Supply `--dataset /path/tasks.parquet` for
a local table. `--no-icl` selects the zero-shot ablation.

```bash
python -m eval.judge --task S01 --model-output agent_output.json
```

The judge obtains S01's English rubric from the table and uses the shared
English instructions in `eval/judge_prompt.md`. Custom rubric files remain
supported through `--rubrics`. Version pins and checksums live in GitHub's
`resources/` configuration, outside the public task table.

The model receives only the public input fields, the selected demonstration,
tool instructions, budgets and observations during exploration. The launcher
saves its assembled initial prompt as `<run-dir>/prompt.txt`. **Rubrics are evaluation answers and are never included in model input.**

The public rubric contains only `anomaly` and `expected`. Reproduction routes
are omitted; conditions necessary to identify a dynamic anomaly remain in
`anomaly`. This is a simplified format for new runs. Published experiment
records retain their original prompts and rubrics (including reproduction
steps); the reported paper scores have not been recomputed with this format.

## Source records and archival experiments

The JSON catalogs in GitHub preserve the authored task definitions and earlier
experiment records. `scripts/export_hf_dataset.py` builds the public task table
from those sources. Regular benchmark runs use the pinned HF table; pass
`--legacy-task-files` to the native or VLA replay launcher only when reproducing
archival tasks outside the paper evaluation split.
