#!/usr/bin/env python3
"""Export per-environment task inputs and evaluation data for release packages."""
import argparse
import ast
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def instruction():
    tree = ast.parse((ROOT / 'scripts/native-agents/launch.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and
                                               t.id == 'DEFAULT_INSTRUCTION' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Default agent instruction not found')


def export(output):
    tasks = json.loads((ROOT / 'benchmark/paper-tasks.json').read_text())['tasks']
    scenes = json.loads((ROOT / 'scripts/native-agents/task-scenes.json').read_text())['scenes']
    categories = json.loads((ROOT / 'scripts/native-agents/task-subcategories.json').read_text())['task_subcategories']
    groups = defaultdict(list)
    for task in tasks:
        family = task['family']
        engine, name = ('three.js', family.removeprefix('threejs_')) if family.startswith('threejs_') else ('unreal', family)
        groups[(engine, name)].append(task)
    inventory = []
    for (engine, name), rows in sorted(groups.items()):
        directory = output / engine / name
        inputs = []
        for task in sorted(rows, key=lambda t: t['id']):
            matching = [s['description'] for s in scenes if task['id'] in s['task_ids']]
            if len(matching) != 1:
                raise ValueError(f"Expected one scene description for {task['id']}")
            inputs.append({'id': task['id'], 'scene_description': matching[0],
                           'subcategory': categories[task['id']]})
        write_json(directory / 'input/tasks.json', {'tasks': inputs})
        (directory / 'input/instruction.txt').write_text(instruction() + '\n')
        shutil.copyfile(ROOT / 'benchmark/taxonomy.json', directory / 'input/taxonomy.json')
        for rel in ['context.json', 'exclude_from_eval.json']:
            destination = directory / 'input/icl' / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'examples/icl' / rel, destination)
        shutil.copytree(ROOT / 'examples/icl/images', directory / 'input/icl/images', dirs_exist_ok=True)
        write_json(directory / 'evaluation/rubrics.json', {'tasks': rows})
        shutil.copyfile(ROOT / 'eval/judge_prompt.md', directory / 'evaluation/judge_prompt.md')
        write_json(directory / 'tasks.json', {'environment': name, 'engine': engine,
                   'tasks': [{'id': t['id'], 'map': t['map'], 'revision': t['revision'],
                              'subcategory': t['paper_subcategory']} for t in rows]})
        (directory / 'DATA.md').write_text('''# Task data

`tasks.json` lists this environment's paper tasks and map identifiers.

## Model input

- `input/instruction.txt`: the native agent's default auditing instruction.
- `input/tasks.json`: scene description and assigned subcategory for each task.
- `input/taxonomy.json`: category definitions.
- `input/icl/`: demonstration text, reference answers and images. The standard
  category-ICL protocol supplies only the assigned subcategory's demonstration.

The model also receives tool instructions, action budgets and observations from
the running environment. The native launcher saves the complete assembled prompt
as `prompt.txt` in each run directory. Static inputs are not an episode recording.

## Evaluation

`evaluation/rubrics.json` contains the benchmark task records, including expected
behavior, reproduction steps and acceptance criteria. These are scoring answers;
do not include them in the tested model's input. `evaluation/judge_prompt.md` is
the scoring prompt. The scoring implementation is in the source repository's
`eval/` directory.
''')
        data_files = [directory / 'tasks.json', directory / 'DATA.md']
        for section in ['input', 'evaluation']:
            data_files.extend(p for p in (directory / section).rglob('*') if p.is_file())
        files = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(data_files)}
        write_json(directory / 'data-checksums.json', files)
        inventory.append({'engine': engine, 'environment': name, 'task_count': len(rows),
                          'archive': f'{engine}/{name}.tar.gz'})
    assert sum(e['task_count'] for e in inventory) == 213
    assert len(inventory) == 13
    write_json(output / 'inventory.json', inventory)
    return inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for row in export(args.output):
        print(row['archive'], row['task_count'])
