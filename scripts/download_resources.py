#!/usr/bin/env python3
"""Restore the published runtime packages and generate local launch profiles."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from environments.unreal_launch import without_hud


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def extract(archive, destination):
    """Only restore directories and regular files; never follow archive links."""
    restored = set()
    with tarfile.open(archive, 'r:gz') as bundle:
        for member in bundle:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe archive path: ' + member.name)
            target = destination / path
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                target.chmod(member.mode & 0o777)
                restored.add(path)
            elif member.islnk():
                source = Path(member.linkname)
                if source.is_absolute() or '..' in source.parts or source not in restored or source == path:
                    raise ValueError('Unsafe archive hard link: ' + member.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                # Reuse verified archive contents without seeking backward through gzip.
                shutil.copyfile(destination / source, target)
                target.chmod(member.mode & 0o777)
                restored.add(path)
            else:
                raise ValueError('Unsupported archive member: ' + member.name)


def builds(package):
    """A download can contain several preserved scene builds."""
    return package.get('variants', [package] if package.get('binary') else [])


def verify_binaries(package, directory, installed=False):
    for build in builds(package):
        if digest(directory / build['binary']) != build['binary_sha256']:
            detail = 'Installed executable was modified' if installed else 'Executable checksum mismatch'
            raise ValueError(detail + ': ' + build['id'])


def download(package, cache, local_archives=None):
    name = package['filename']
    path = (local_archives or cache) / name
    if path.exists() and digest(path) == package['sha256']:
        return path
    if local_archives:
        raise ValueError('Missing or mismatched local archive: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    url = (f"https://huggingface.co/datasets/{package['repository']}/resolve/"
           f"{package['revision']}/{name}")
    context = ssl.create_default_context()
    try:
        import certifi
        context.load_verify_locations(certifi.where())
    except ImportError:
        pass
    partial = path.with_suffix(path.suffix + '.part')
    print(f"Downloading {name} ({package['bytes'] / 1e9:.2f} GB)", flush=True)
    with urllib.request.urlopen(url, context=context, timeout=120) as source, partial.open('wb') as output:
        shutil.copyfileobj(source, output, 8 * 1024 * 1024)
    if partial.stat().st_size != package['bytes'] or digest(partial) != package['sha256']:
        raise ValueError('Download checksum mismatch: ' + name)
    partial.replace(path)
    return path


def restore(package, root, cache, local_archives=None, keep=False):
    destination = root / package['id']
    marker = destination / '.worldauditbench-release.json'
    if marker.exists() and json.loads(marker.read_text())['sha256'] == package['sha256']:
        verify_binaries(package, destination, installed=True)
        print('Already restored: ' + package['id'], flush=True)
        return
    if destination.exists():
        raise ValueError('Destination already exists without a matching release: ' + str(destination))
    archive = download(package, cache, local_archives)
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.restore-', dir=root))
    try:
        extract(archive, staging)
        verify_binaries(package, staging)
        (staging / '.worldauditbench-release.json').write_text(json.dumps(package, indent=2) + '\n')
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    if not keep and not local_archives:
        archive.unlink()
    print('Restored: ' + package['id'], flush=True)


def write_profiles(manifest, root):
    reference = json.loads((ROOT / 'data/benchmark/profiles/ue-aws-profiles-20260918.json').read_text())
    original = reference['tasks']
    original.update(json.loads((ROOT / 'data/benchmark/profiles/ue-urban-ipc-profiles-20260920.json').read_text())['tasks'])
    tasks = {}
    policies = {}
    for path in (ROOT / 'data/benchmark/policies').glob('*/policy.json'):
        policies[digest(path)] = path.resolve()
    for package in manifest['packages']:
        if package['group'] != 'unreal-runtime' or not (root / package['id'] / '.worldauditbench-release.json').is_file():
            continue
        task_builds = {task: build for build in builds(package) for task in build['tasks']}
        if set(task_builds) != set(package['tasks']):
            raise ValueError('Variant task coverage differs: ' + package['id'])
        for task_id in package['tasks']:
            build = task_builds[task_id]
            profile = copy.deepcopy(original[task_id])
            if profile['build_sha256'] != build['binary_sha256']:
                raise ValueError('Release differs from experiment build: ' + task_id)
            profile['binary'] = str(root / package['id'] / build['binary'])
            expected = reference['policies'][profile['policy_version']]['sha256']
            policy = policies.get(expected)
            if policy is None:
                raise ValueError('Missing or modified exploration policy: ' + profile['policy_version'])
            profile['policy_path'] = str(policy)
            profile['policy_sha256'] = expected
            profile['extra_args'] = [('-AuditorExplorationPolicy=' + str(policy)) if arg.lower().startswith('-auditorexplorationpolicy=') else arg for arg in profile.get('extra_args', [])]
            profile['game_args'] = without_hud(profile.get('game_args', []))
            profile['hud'] = 'disabled-in-engine'
            tasks[task_id] = profile
    path = root / 'unreal-profiles.json'
    path.write_text(json.dumps({'tasks': tasks}, indent=2) + '\n')
    print(f'Wrote {len(tasks)} task profiles: {path}', flush=True)


def restore_examples(root):
    images = root / 'icl-examples/examples/icl/images'
    if not images.is_dir():
        images = root / 'icl-examples/icl/images'
    if not images.is_dir():
        return
    for entry in json.loads((ROOT / 'data/resources/manifest.json').read_text())['resources']:
        if entry['group'] != 'icl-examples':
            continue
        source = images / Path(entry['path']).name
        target = ROOT / entry['path']
        if digest(source) != entry['sha256']:
            raise ValueError('Example image checksum mismatch: ' + source.name)
        if target.exists() and digest(target) != entry['sha256']:
            raise ValueError('Refusing to overwrite a different image: ' + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
    print('Restored ICL images to data/examples/icl/images and service example directories.', flush=True)


def write_browser_profiles(root, manifest=None):
    manifest = manifest or json.loads((ROOT / 'data/resources/releases.json').read_text())
    standalone = [p for p in manifest['packages'] if p['group'] == 'threejs-runtime'
                  and (root / p['id'] / '.worldauditbench-release.json').is_file()]
    if standalone:
        catalog = {t['id']: t for t in json.loads((ROOT / 'data/benchmark/paper-tasks.json').read_text())['tasks']}
        from urllib.parse import urlparse
        output = root / 'browser-profiles'
        output.mkdir(exist_ok=True)
        count = 0
        for package in standalone:
            pages = root / package['id'] / package['runtime_root']
            checked = set()
            for task_id in package['tasks']:
                row = catalog[task_id]
                filename = Path(urlparse(row['map']).path).name
                checksum = row['page_sha256']
                if filename not in checked:
                    if digest(pages / filename) != checksum:
                        raise ValueError('Browser page checksum mismatch: ' + filename)
                    checked.add(filename)
                config = {'task': task_id, 'browser_root': str(pages), 'browser_page': filename,
                          'browser_case': row['source_case'], 'page_sha256': checksum}
                (output / (task_id + '.json')).write_text(json.dumps(config, indent=2) + '\n')
                count += 1
        print(f'Wrote {count} browser task configurations: {output}', flush=True)
        return
    pages = root / 'threejs-builds'
    if not (pages / '.worldauditbench-release.json').is_file():
        return
    from urllib.parse import urlparse
    assigned = set((ROOT / 'data/benchmark/splits/threejs.txt').read_text().splitlines())
    output = root / 'browser-profiles'
    output.mkdir(exist_ok=True)
    checked = set()
    for task in json.loads((ROOT / 'data/benchmark/tasks.json').read_text())['tasks']:
        if task['id'] not in assigned:
            continue
        filename = Path(urlparse(task['map']).path).name
        identity = (filename, task['page_sha256'])
        if identity not in checked:
            if digest(pages / filename) != task['page_sha256']:
                raise ValueError('Browser page checksum mismatch: ' + filename)
            checked.add(identity)
        config = {'task': task['id'], 'browser_root': str(pages), 'browser_page': filename,
                  'browser_case': task['source_case'], 'page_sha256': task['page_sha256']}
        (output / (task['id'] + '.json')).write_text(json.dumps(config, indent=2) + '\n')
    print(f'Wrote {len(assigned)} browser task configurations: {output}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/resources/releases.json')
    parser.add_argument('--root', type=Path, default=ROOT / 'out/runtime')
    parser.add_argument('--package', action='append', help='Select a package; repeat for multiple packages.')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--keep-archives', action='store_true')
    parser.add_argument('--local-archives', type=Path, help='Restore already downloaded archives.')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    requested = set(args.package or [])
    if 'threejs-builds' in requested and any(p['group'] == 'threejs-runtime' for p in manifest['packages']):
        requested.remove('threejs-builds')
        requested.update(p['id'] for p in manifest['packages'] if p['group'] == 'threejs-runtime')
    selected = [p for p in manifest['packages'] if not requested or p['id'] in requested]
    unknown = requested - {p['id'] for p in selected}
    if unknown:
        parser.error('Unknown packages: ' + ', '.join(sorted(unknown)))
    if args.list:
        for package in selected:
            print(f"{package['id']:24} {package['bytes'] / 1e9:5.2f} GB  {package['group']}")
        return
    root = args.root.expanduser().resolve()
    for package in selected:
        restore(package, root, root / '.downloads', args.local_archives, args.keep_archives)
    write_profiles(manifest, root)
    restore_examples(root)
    write_browser_profiles(root, manifest)


if __name__ == '__main__':
    main()
