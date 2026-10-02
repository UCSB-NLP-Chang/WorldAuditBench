#!/usr/bin/env python3
"""Export runnable task catalogs referencing the shared Hugging Face dataset."""
import argparse
import ast
from collections import defaultdict
import hashlib
import json
from pathlib import Path

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
    groups = defaultdict(list)
    for task in tasks:
        family = task['family']
        engine, name = ('three.js', family.removeprefix('threejs_')) if family.startswith('threejs_') else ('unreal', family)
        groups[(engine, name)].append(task)
    inventory = []
    for (engine, name), rows in sorted(groups.items()):
        directory = output / engine / name
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory / 'tasks.json', {'environment': name, 'engine': engine,
                   'tasks': [{'id': t['id'], 'map': t['map'], 'revision': t['revision'],
                              'subcategory': t['paper_subcategory']} for t in rows]})
        (directory / 'DATA.md').write_text("""# Task data

This archive contains the runnable environment and its task identifiers.

The shared task table, model inputs and evaluation rubrics are published at:
https://huggingface.co/datasets/ziyjiang/WorldAuditBench/tree/main/dataset

In-context demonstrations are stored once at:
https://huggingface.co/datasets/ziyjiang/WorldAuditBench/tree/main/examples

Use the task ID to join the environment with the task table. The GitHub launchers
load the pinned dataset and shared examples automatically. Rubrics are scoring
answers and must not be included in the tested model's input.
""")
        data_files = [directory / 'tasks.json', directory / 'DATA.md']
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
