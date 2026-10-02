#!/usr/bin/env python3
"""Verify standalone Three.js archives, task coverage and local serving."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from urllib.error import HTTPError
from urllib.request import urlopen


def check(archive):
    with tempfile.TemporaryDirectory(prefix='worldauditbench-check-') as temporary:
        root = Path(temporary)
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                    raise ValueError(f'Unsafe archive member: {member.name}')
            bundle.extractall(root, filter='data')
        directories = list(root.iterdir())
        assert len(directories) == 1
        package = directories[0]
        manifest = json.loads((package / 'launch.json').read_text())
        assert manifest['engine'] == 'three.js'
        tasks = manifest['tasks']
        inputs = json.loads((package / 'input/tasks.json').read_text())['tasks']
        rubrics = json.loads((package / 'evaluation/rubrics.json').read_text())['tasks']
        assert set(tasks) == {t['id'] for t in inputs} == {t['id'] for t in rubrics}
        for task in inputs:
            assert set(task) == {'id', 'scene_description', 'subcategory'}
        for name, expected in json.loads((package / 'data-checksums.json').read_text()).items():
            assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected, name
        listed = subprocess.check_output([sys.executable, str(package / 'run.py'), '--list'], text=True)
        assert set(listed.splitlines()) == set(tasks)
        for page in {t['page'] for t in tasks.values()}:
            digest = hashlib.sha256((package / 'runtime' / page).read_bytes()).hexdigest()
            assert all(t['page_sha256'] == digest for t in tasks.values() if t['page'] == page)
        first = next(iter(tasks))
        process = subprocess.Popen([sys.executable, '-u', str(package / 'run.py'), first,
                                    '--no-browser', '--port', '0'], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True)
        try:
            import select
            ready, _, _ = select.select([process.stdout], [], [], 20)
            assert ready, 'Launcher did not print a URL within 20 seconds'
            url = process.stdout.readline().strip()
            with urlopen(url, timeout=20) as response:
                assert hashlib.sha256(response.read()).hexdigest() == tasks[first]['page_sha256']
            origin = url.rsplit('/', 1)[0]
            try:
                urlopen(origin + '/evaluation/rubrics.json', timeout=10)
                raise AssertionError('Evaluation answers are exposed by the environment server')
            except HTTPError as error:
                assert error.code == 404
        finally:
            process.terminate()
            process.wait(timeout=10)
        return list(tasks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    seen = set()
    for archive in sorted(args.directory.glob('*.tar.gz')):
        task_ids = check(archive)
        assert not seen.intersection(task_ids), 'Duplicate task across archives'
        seen.update(task_ids)
        print(f'{archive.name}: {len(task_ids)} tasks passed', flush=True)
    assert len(seen) == 87, f'Expected 87 Three.js tasks; found {len(seen)}'
