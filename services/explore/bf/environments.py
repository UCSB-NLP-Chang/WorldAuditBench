"""Public scene background only, separate from bug answers and immutable task versions."""
import json
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name('environment-descriptions.json').read_text())

def description_for(task_id):
    return catalog().get(task_id)
