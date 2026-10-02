"""Read task inputs and evaluation answers from the pinned Hugging Face dataset."""
import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import tempfile
import tarfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / 'out/dataset/tasks.parquet'
PIN = ROOT / 'data/resources/dataset.json'
DEFAULT_EXAMPLES = ROOT / 'out/dataset/examples'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_dataset():
    """Download once, verify the release hash, and atomically populate the cache."""
    return download_file(json.loads(PIN.read_text()), DEFAULT_DATASET)


def download_file(pin, destination):
    destination = Path(destination)
    if destination.is_file() and sha256(destination) == pin['sha256']:
        return destination
    import requests
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/datasets/{pin['repository']}/resolve/{pin['revision']}/{pin['filename']}"
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.partial', delete=False) as temporary:
        path = Path(temporary.name)
        try:
            with requests.get(url, stream=True, timeout=(15, 120)) as response:
                response.raise_for_status()
                for chunk in response.iter_content(8 * 1024 * 1024):
                    temporary.write(chunk)
            temporary.close()
            if path.stat().st_size != pin['bytes'] or sha256(path) != pin['sha256']:
                raise ValueError('Hugging Face task dataset checksum mismatch')
            path.replace(destination)
        finally:
            path.unlink(missing_ok=True)
    return destination


def example_checksum(subcategory):
    return json.loads(PIN.read_text())['examples']['category_checksums'][subcategory]


def ensure_examples():
    pin = json.loads(PIN.read_text())['examples']
    marker = DEFAULT_EXAMPLES / '.release-sha256'
    if marker.is_file() and marker.read_text().strip() == pin['sha256']:
        return DEFAULT_EXAMPLES / 'icl'
    archive = download_file(pin, DEFAULT_EXAMPLES.parent / 'icl-examples.tar.gz')
    with tempfile.TemporaryDirectory(dir=DEFAULT_EXAMPLES.parent, prefix='examples-') as temporary:
        staging = Path(temporary)
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                parts = Path(member.name)
                if parts.is_absolute() or '..' in parts.parts or not (member.isfile() or member.isdir()):
                    raise ValueError('Unsafe example archive member')
            bundle.extractall(staging, filter='data')
        from agent.vlm.mcp.examples import ExamplePack
        ExamplePack(staging / 'icl')
        (staging / '.release-sha256').write_text(pin['sha256'] + '\n')
        if DEFAULT_EXAMPLES.exists():
            if marker.is_file() and marker.read_text().strip() == pin['sha256']:
                return DEFAULT_EXAMPLES / 'icl'
            raise ValueError('Example cache differs from release; move it aside before downloading')
        try:
            staging.rename(DEFAULT_EXAMPLES)
        except OSError:
            if not (marker.is_file() and marker.read_text().strip() == pin['sha256']):
                raise
    return DEFAULT_EXAMPLES / 'icl'


@lru_cache(maxsize=4)
def _catalog(path, modified_ns, size):
    import pyarrow.parquet as pq
    columns = ['task_id', 'engine', 'environment', 'category', 'subcategory',
               'map', 'input', 'rubric']
    rows = pq.read_table(path, columns=columns).to_pylist()
    catalog = {r['task_id'].casefold(): r for r in rows}
    if len(catalog) != len(rows):
        raise ValueError('Duplicate task IDs in dataset')
    return catalog


def load_task(task_id, dataset=None):
    path = Path(dataset) if dataset is not None else ensure_dataset()
    stat = path.stat()
    catalog = _catalog(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    key = task_id.strip().casefold()
    if key not in catalog:
        raise ValueError(f'Task {task_id} is absent from the paper dataset; use --legacy-task-files for archival tasks')
    row = copy.deepcopy(catalog[key])
    return row
