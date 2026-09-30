"""Bilingual instructions and Markdown exported from the same public definitions."""
import json
from pathlib import Path
from .taxonomy import taxonomy_text
from .common import require

INSTRUCTIONS = json.loads(Path(__file__).with_name('instructions.json').read_text())

def markdown(lang):
    require(lang in ('zh', 'en'), 'Unknown language', 404)
    data = INSTRUCTIONS[lang]
    lines = ['# ' + data['title'], '', data['intro'], '']
    for section in data['sections']:
        lines += ['## ' + section['title'], '']
        lines += ['- ' + item for item in section['items']]
        lines += ['']
    lines += ['## ' + ('全部 bug 类型' if lang == 'zh' else 'Complete bug taxonomy'), '']
    lines += [taxonomy_text(lang), '']
    lines += ['## ' + data['report_title'], '', '```text', data['template'], '```', '', data['agent_note'], '']
    return '\n'.join(lines)
