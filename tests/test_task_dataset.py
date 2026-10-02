"""The public task table drives inputs and judging without exposing task answers."""
import importlib.util
import json
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from auditor import task_dataset
from eval import judge

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def table(tmp_path):
    row = {'task_id': 'S01', 'engine': 'unreal', 'environment': 'subway',
           'category': 'Static physics', 'subcategory': 'G1',
           'input': {'instruction': 'Inspect this public scene.',
                     'scene_description': 'A station concourse.', 'subcategory': 'G1'},
           'rubric': {'text': 'HIDDEN_RUBRIC_ANSWER: floating bench',
                      'en': {'criteria': 'Bench floats'}, 'zh': {'criteria': '长椅悬空'}},
           'judge_prompt': 'Dataset-specific judge instructions.',
           'runtime': {'map': '/Game/Test', 'revision': 1, 'source_case': None},
           'provenance': {'source_commit': 'synthetic-test', 'icl_sha256': 'unused'}}
    path = tmp_path / 'tasks.parquet'
    pq.write_table(pa.Table.from_pylist([row]), path)
    return path


def test_task_lookup_and_unknown_id(table):
    assert task_dataset.load_task('s01', table)['input']['scene_description'] == 'A station concourse.'
    with pytest.raises(ValueError, match='absent from the paper dataset'):
        task_dataset.load_task('S99', table)


def test_launcher_uses_dataset_instruction_without_rubric(table, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('dataset_launcher', ROOT / 'scripts/native-agents/launch.py')
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    base = tmp_path / 'native'
    (base / 'venv/bin').mkdir(parents=True)
    (base / 'venv/bin/python').symlink_to(sys.executable)
    monkeypatch.setattr(launch, 'BASE', base)
    args = launch.cli_parser().parse_args([
        'codex', '--environment', 'unreal-http', '--env-url', 'http://127.0.0.1:19100',
        '--task', 'S01', '--dataset', str(table), '--no-icl', '--dry-run', '--cli', '/bin/true',
        '--run-dir', str(tmp_path / 'run')])
    _, _, _, prompt, manifest = launch.prepare(args)
    assert 'Inspect this public scene.' in prompt
    assert 'A station concourse.' in prompt
    for name in ['prompt.txt', 'launch.json', 'episode-config.json']:
        assert 'HIDDEN_RUBRIC_ANSWER' not in (tmp_path / 'run' / name).read_text()
    assert manifest['scene_description'] == 'A station concourse.'


def test_judge_reads_same_task_and_prompt(table, tmp_path, monkeypatch):
    report = tmp_path / 'report.txt'
    report.write_text('A bench floats above the floor.')
    def fake_judge(rubric, model_output, images, **kwargs):
        assert rubric == 'HIDDEN_RUBRIC_ANSWER: floating bench'
        assert kwargs['instructions'] == 'Dataset-specific judge instructions.'
        return {'reason': 'Test comparison', 'score': 1}
    monkeypatch.setattr(judge, 'judge', fake_judge)
    assert judge.main(['--task', 'S01', '--dataset', str(table), '--model-output', str(report)]) == 0


def test_duplicate_ids_rejected(table):
    row = pq.read_table(table).to_pylist()[0]
    pq.write_table(pa.Table.from_pylist([row, row]), table)
    with pytest.raises(ValueError, match='Duplicate task IDs'):
        task_dataset.load_task('S01', table)
