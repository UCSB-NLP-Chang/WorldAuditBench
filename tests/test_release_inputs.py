"""Every paper task must launch with its authored public input metadata."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_launch_inputs', ROOT / 'scripts/native-agents/launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


def test_all_paper_tasks_resolve_without_manual_input_overrides():
    tasks = json.loads((ROOT / 'benchmark/paper-tasks.json').read_text())['tasks']
    for task in tasks:
        engine = 'threejs' if task['family'].startswith('threejs_') else 'unreal-http'
        args = launch.cli_parser().parse_args(['codex', '--environment', engine, '--task', task['id'], '--legacy-task-files'])
        assert launch.task_subcategory(args) == task['paper_subcategory'], task['id']
        assert launch.scene_description(args).strip(), task['id']
