"""Read-only presentation of versioned, sanitized teaching examples."""
import json
import re
from functools import lru_cache
from pathlib import Path
from .common import require

ROOT = Path(__file__).resolve().parents[1] / 'example-assets'

@lru_cache(maxsize=1)
def catalog():
    return json.loads((ROOT / 'catalog.json').read_text())

@lru_cache(maxsize=1)
def annotations():
    return json.loads((ROOT / 'annotations.json').read_text())

def example_for(task_id):
    data = catalog()
    match = data['tasks'].get(task_id)
    if not match:
        return {'example': None, 'version': data['version']}
    marks = annotations()
    example = dict(data['examples'][match['code']])
    example['frames'] = [dict(frame, boxes=marks['images'].get(Path(frame['image_path']).name, {}).get('boxes', [])) for frame in example['frames']]
    return {'example': example, 'related': match['related'], 'version': data['version'], 'annotation_version': marks['version']}

def image(name):
    require(re.fullmatch(r'[GCVTS][1-4]_[0-9]{2}\.png', name), 'Not found', 404)
    allowed = {Path(f['image_path']).name for e in catalog()['examples'].values() for f in e['frames']}
    require(name in allowed, 'Not found', 404)
    return (ROOT / 'images' / name).read_bytes()
