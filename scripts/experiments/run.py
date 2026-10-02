#!/usr/bin/env python3
"""Run one agent on selected tasks with the paper's default settings."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.runtime import DEFAULT_RUNTIME, ensure_environment, server_command, stop, task_catalog, wait_ready

PRESETS = Path(__file__).with_name('agents.json')


def task_ids(value):
    if value.startswith('@'):
        rows = Path(value[1:]).read_text().splitlines()
    else:
        rows = value.split(',')
    ids = [s.strip() for s in rows if s.strip()]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Provide a nonempty list of unique task IDs')
    unknown = set(ids) - set(task_catalog())
    if unknown:
        raise ValueError('Unknown tasks: ' + ', '.join(sorted(unknown)))
    return ids


def agent_command(preset, task, runtime, output, port, budget, examples=True, model=None, extra=()):
    catalog = task_catalog()
    browser = catalog[task]['family'].startswith('threejs_')
    command = [sys.executable, str(ROOT / 'agent/vlm/native/launch.py'), preset['client'],
               '--model', model or preset['model'], '--task', task,
               '--environment', 'threejs' if browser else 'unreal-http',
               '--seed', '5' if browser else '0', '--max-actions', str(budget),
               '--max-tool-calls', '400', '--require-full-budget', '--observation', 'on-demand',
               '--run-dir', str(output), *preset['args']]
    command += (['--browser-config', str(runtime / 'browser-profiles' / (task + '.json'))] if browser
                else ['--env-url', f'http://127.0.0.1:{port}'])
    if not examples:
        command.append('--no-icl')
    return command + list(extra)


def export_report(run):
    """Export only final agent findings and their cited frames for judging."""
    path = run / 'meta.json'
    if not path.exists():
        raise RuntimeError('Agent did not write an episode result: ' + str(path))
    meta = json.loads(path.read_text())
    flags = [f for f in meta.get('flags', []) if f.get('status') != 'retracted']
    report = {'findings': flags, 'summary': meta.get('done_summary', '')}
    (run / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    refs = {ref for flag in flags for ref in flag.get('evidence', [])}
    index = run / 'frames/index.jsonl'
    rows = [json.loads(line) for line in index.read_text().splitlines() if line.strip()] if index.exists() else []
    images = [str((run / 'frames' / row['file']).resolve()) for row in rows if row['ref'] in refs]
    (run / 'evidence.json').write_text(json.dumps(images, indent=2) + '\n')
    return meta.get('status')


def main(argv=None):
    presets = json.loads(PRESETS.read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=presets, required=True)
    parser.add_argument('--tasks', required=True, help='Comma-separated IDs or @path/to/split.txt')
    parser.add_argument('--model', help='Override the model ID in the selected preset')
    parser.add_argument('--max-actions', type=int, default=40)
    parser.add_argument('--no-icl', action='store_true')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--runtime-root', type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--gpu', type=int, default=0)
    parser.add_argument('--port', type=int, default=19100)
    parser.add_argument('--dry-run', action='store_true', help='Print commands without downloading or calling a model')
    parser.add_argument('client_args', nargs=argparse.REMAINDER, help='Extra client options after --')
    args = parser.parse_args(argv)
    if args.max_actions < 1:
        parser.error('--max-actions must be positive')
    try:
        tasks = task_ids(args.tasks)
    except ValueError as exc:
        parser.error(str(exc))
    runtime = args.runtime_root.expanduser().resolve()
    output = (args.output or ROOT / 'out/runs' / args.agent).expanduser().resolve()
    extra = args.client_args[1:] if args.client_args[:1] == ['--'] else args.client_args
    catalog = task_catalog()
    results = json.loads((output / "results.json").read_text()) if (output / "results.json").exists() and not args.dry_run else []
    for task in tasks:
        run = output / task
        command = agent_command(presets[args.agent], task, runtime, run, args.port,
                                args.max_actions, not args.no_icl, args.model, extra)
        unreal = not catalog[task]['family'].startswith('threejs_')
        if args.dry_run:
            if unreal:
                print(shlex.join(server_command(task, runtime, args.gpu, args.port)))
            print(shlex.join(command))
            continue
        if run.exists():
            parser.error('Run already exists; choose a new --output: ' + str(run))
        if unreal and sys.platform != 'linux':
            parser.error('Unreal tasks require a Linux GPU host')
        ensure_environment(task, runtime, args.download)
        output.mkdir(parents=True, exist_ok=True)
        process = None
        log = None
        try:
            if unreal:
                log = (output / (task + '-environment.log')).open('wb')
                process = subprocess.Popen(server_command(task, runtime, args.gpu, args.port),
                                           stdout=log, stderr=subprocess.STDOUT)
                wait_ready(process, args.port)
            result = subprocess.run(command)
            status = export_report(run) if result.returncode == 0 else 'client_failed'
            results.append({'task': task, 'exit_code': result.returncode, 'status': status, 'run': str(run)})
        finally:
            stop(process)
            if log:
                log.close()
        (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    return 1 if any(row['exit_code'] or row['status'] != 'completed' for row in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
