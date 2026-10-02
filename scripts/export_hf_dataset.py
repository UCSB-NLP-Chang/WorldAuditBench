#!/usr/bin/env python3
"""Export all 213 tasks, model inputs and rubrics to one HF dataset."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from auditor.mcp_agent.examples import ExamplePack
from export_environment_metadata import instruction


def export(destination):
    from datasets import Dataset, Features, Value
    import pyarrow.parquet as pq

    tasks = json.loads((ROOT / 'benchmark/paper-tasks.json').read_text())['tasks']
    scenes = json.loads((ROOT / 'scripts/native-agents/task-scenes.json').read_text())['scenes']
    categories = json.loads((ROOT / 'scripts/native-agents/task-subcategories.json').read_text())['task_subcategories']
    packs = {code: ExamplePack(ROOT / 'examples/icl', code=code)
             for code in {t['paper_subcategory'] for t in tasks}}
    rows = []
    for task in tasks:
        tid, code = task['id'], task['paper_subcategory']
        packs[code].check_task(tid)
        assert categories[tid] == code
        descriptions = [s['description']['en'] for s in scenes if tid in s['task_ids']]
        assert len(descriptions) == 1, tid
        rows.append({
            'task_id': tid,
            'engine': 'three.js' if task['family'].startswith('threejs_') else 'unreal',
            'environment': task['family'].removeprefix('threejs_'),
            'category': task['paper_family'], 'subcategory': code,
            'input': {'instruction': instruction(), 'scene_description': descriptions[0]},
            'map': task['map'],
            'rubric': {'anomaly': task['rubrics_i18n']['en']['criteria'],
                       'expected': task['rubrics_i18n']['en']['expected']},
        })
    text = Value('string')
    features = Features({
        'task_id': text, 'engine': text, 'environment': text, 'category': text, 'subcategory': text,
        'map': text,
        'input': {'instruction': text, 'scene_description': text},
        'rubric': {'anomaly': text, 'expected': text},
    })
    for row in rows:
        if re.search(r'[\u3400-\u4dbf\u4e00-\u9fff]', json.dumps(row, ensure_ascii=False)):
            raise ValueError(f"Non-English text remains in task {row['task_id']}")
    dataset = Dataset.from_list(rows, features=features)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(dataset.data.table, destination, row_group_size=213, compression='zstd',
                   use_dictionary=True, dictionary_pagesize_limit=128 * 1024 * 1024)
    # Validate every task field after writing and reading the Parquet file.
    restored = pq.read_table(destination).to_pylist()
    assert len(restored) == 213 and len({r['task_id'] for r in restored}) == 213
    for source, row in zip(rows, restored):
        assert source == row, source['task_id']
    print(json.dumps({'file': str(destination), 'tasks': len(restored),
                      'environments': len({r['environment'] for r in restored}),
                      'bytes': destination.stat().st_size,
                      'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.output)
