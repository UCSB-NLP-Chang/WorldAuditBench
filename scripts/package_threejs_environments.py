#!/usr/bin/env python3
"""Build one standalone archive per released Three.js environment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def package(pages, metadata, output):
    tasks = json.loads((ROOT / 'data/benchmark/paper-tasks.json').read_text())['tasks']
    results = []
    for directory in sorted((metadata / 'three.js').iterdir()):
        if not directory.is_dir():
            continue
        rows = [t for t in tasks if t['family'] == 'threejs_' + directory.name]
        filenames = {Path(urlparse(t['map']).path).name for t in rows}
        assert len(filenames) == 1
        filename = filenames.pop()
        source = pages / filename
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        assert all(t['page_sha256'] == checksum for t in rows)
        (directory / 'runtime').mkdir(exist_ok=True)
        shutil.copyfile(source, directory / 'runtime' / filename)
        notices = directory / 'attribution'
        notices.mkdir(exist_ok=True)
        shutil.copyfile(ROOT / 'THIRD_PARTY.md', notices / 'THIRD_PARTY.md')
        for path in (ROOT / 'environments/threejs/scenes/src').rglob('*'):
            if path.is_file() and (path.name.lower().startswith(('license', 'copying', 'notice'))
                                   or path.name == 'README.md'):
                destination = notices / path.relative_to(ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
        shutil.copyfile(ROOT / 'scripts/environment_runner.py', directory / 'run.py')
        (directory / 'run.sh').write_text('#!/bin/sh\nexec python3 "$(dirname "$0")/run.py" "$@"\n')
        (directory / 'run.sh').chmod(0o755)
        launch = {'engine': 'three.js', 'tasks': {t['id']: {
            'page': filename, 'case': t['source_case'], 'page_sha256': checksum} for t in rows}}
        (directory / 'launch.json').write_text(json.dumps(launch, indent=2) + '\n')
        (directory / 'README.md').write_text(f'''# WorldAuditBench — {directory.name}

Requires Python 3 and a browser with WebGL support.

```sh
./run.sh --list
./run.sh {rows[0]['id']}
```

The command opens the assigned task in your browser. Use WASD and the mouse to
explore. The benchmark overlay is hidden by default. Press Ctrl+C in the terminal
to stop the local server. `--no-browser` prints the URL without opening a browser;
`--port 8766` selects another port.

See `DATA.md` for the shared task dataset and in-context demonstrations. `runtime/`
contains the pinned standalone page used by the benchmark.
''')
        archive = output / 'three.js' / (directory.name + '.tar.gz')
        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, 'w:gz', compresslevel=1) as bundle:
            bundle.add(directory, arcname=directory.name)
        h = hashlib.sha256()
        with archive.open('rb') as f:
            for block in iter(lambda: f.read(8*1024*1024), b''):
                h.update(block)
        results.append({'filename': 'three.js/' + archive.name, 'bytes': archive.stat().st_size,
                        'sha256': h.hexdigest(), 'tasks': [t['id'] for t in rows]})
        print(archive, archive.stat().st_size, flush=True)
    (output / 'threejs-packages.json').write_text(json.dumps(results, indent=2) + '\n')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package(args.pages, args.metadata, args.output)
