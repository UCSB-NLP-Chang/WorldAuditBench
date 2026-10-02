#!/usr/bin/env python3
"""Export all 213 tasks, model inputs and rubrics to one HF dataset."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

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
    judge_prompt = (ROOT / 'eval/judge_prompt.md').read_text()
    source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
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
            'input': {'instruction': instruction(), 'scene_description': descriptions[0],
                      'subcategory': code},
            'rubric': {'text': task['rubrics'], **task['rubrics_i18n']},
            'judge_prompt': judge_prompt,
            'runtime': {'map': task['map'], 'source_case': task.get('source_case'),
                        'revision': task['revision']},
            'provenance': {'source_commit': source_commit, 'task_sha256': task.get('sha256'),
                           'paper_binary_sha256': task.get('build_sha256'),
                           'page_sha256': task.get('page_sha256'),
                           'policy_sha256': task.get('policy_sha256'),
                           'icl_sha256': packs[code].sha256},
        })
    text = Value('string')
    rubric_language = {'expected': text, 'steps': text, 'criteria': text}
    features = Features({
        'task_id': text, 'engine': text, 'environment': text, 'category': text, 'subcategory': text,
        'input': {'instruction': text, 'scene_description': text, 'subcategory': text},
        'rubric': {'text': text, 'en': rubric_language, 'zh': rubric_language},
        'judge_prompt': text,
        'runtime': {'map': text, 'source_case': text, 'revision': Value('int64')},
        'provenance': {key: text for key in ['source_commit', 'task_sha256', 'paper_binary_sha256',
                                            'page_sha256', 'policy_sha256', 'icl_sha256']},
    })
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
