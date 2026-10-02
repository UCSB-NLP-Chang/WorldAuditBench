"""Public taxonomy only: deliberately excludes task mappings and ground truth."""
import json
from pathlib import Path
from .common import require

TAXONOMY = json.loads(Path(__file__).with_name('taxonomy.json').read_text())
CODES = {group['id'] for group in TAXONOMY['categories']} | set(TAXONOMY['legacy']) | {'other', 'unsure'}

def taxonomy_text(lang):
    lines = [TAXONOMY['intro'][lang]]
    lines += [f"({group['number']}) {group['name'][lang]}: {group['description'][lang]}" for group in TAXONOMY['categories']]
    return '\n'.join(lines + [TAXONOMY['principle'][lang]])

def category(value):
    require(isinstance(value, str) and value in CODES, '请选择有效的 bug category')
    return value
