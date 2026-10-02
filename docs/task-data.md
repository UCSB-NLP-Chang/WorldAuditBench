# Task rubrics and model inputs

The paper evaluation set contains **213 tasks: 126 Unreal and 87 Three.js**.
Use task IDs to join the files below.

| Content | Location | Purpose |
| --- | --- | --- |
| Task definitions and answers | [`benchmark/paper-tasks.json`](../benchmark/paper-tasks.json) | The `tasks` array contains each task's ID, map, revision, category and rubric. |
| Rubric text | `rubrics` and `rubrics_i18n` in each task record | Expected behavior, reproduction steps and acceptance criteria, including English and Chinese versions. These are evaluation answers. |
| Evaluation split | [`benchmark/splits/`](../benchmark/splits/) | The fixed paper evaluation task lists. |
| Public scene description | [`scripts/native-agents/task-scenes.json`](../scripts/native-agents/task-scenes.json) | The native launcher selects the description whose `task_ids` contains the requested task. |
| Assigned anomaly subcategory | [`scripts/native-agents/task-subcategories.json`](../scripts/native-agents/task-subcategories.json) | Selects the subcategory and its demonstration in the category-ICL protocol. |
| Auditing instruction and prompt assembly | [`scripts/native-agents/launch.py`](../scripts/native-agents/launch.py) | `DEFAULT_INSTRUCTION`, tool guidance, action budgets and protocol options. |
| In-context demonstrations | [`examples/icl/context.json`](../examples/icl/context.json) | Demonstration text and image references; download the associated images using the resource instructions. |
| Judge prompt and implementation | [`eval/judge_prompt.md`](../eval/judge_prompt.md), [`eval/judge.py`](../eval/judge.py) | Scores the agent report against the task rubric. |

`benchmark/tasks.json` also contains baseline and review entries. Use
`benchmark/paper-tasks.json` for the 213-task paper evaluation set.

## Inspect a task

Run this from the repository root:

```python
import json
from pathlib import Path

task_id = "S01"
tasks = json.loads(Path("benchmark/paper-tasks.json").read_text())["tasks"]
task = next(t for t in tasks if t["id"] == task_id)
print(task["map"])
print(task["rubrics_i18n"]["en"])
```

## What the tested model receives

The default native-agent launcher combines the auditing instruction, a public
scene description, the selected category demonstration, tool instructions and
budgets. The environment supplies observations during exploration. The launcher
saves the assembled initial prompt as `<run-dir>/prompt.txt`; command-line
overrides and ablation settings can change that prompt.

Task titles, rubrics, reproduction steps and acceptance criteria describe the
target anomaly. Keep them out of the tested model's input. Demonstration answers
belong to the ICL protocol and concern separate example tasks.

## Per-environment release data

`scripts/export_environment_metadata.py` exports the following structure for
each of the 13 environment packages:

```text
tasks.json                 Task IDs, maps, revisions and subcategories
input/instruction.txt      Default auditing instruction
input/tasks.json           Public scene description and subcategory per task
input/taxonomy.json         Category definitions
input/icl/                 Demonstration text and images
evaluation/rubrics.json    Corresponding task records and answers
evaluation/judge_prompt.md Judge prompt
DATA.md                    Input and evaluation usage notes
data-checksums.json         Checksums of the exported task data
```

These files are being incorporated into the reorganized environment archives.
The existing flat Hugging Face archives predate this layout; use the GitHub
paths above until the replacement archives are published.
