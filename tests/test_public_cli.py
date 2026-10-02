import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.experiments.run import PRESETS, agent_command, export_report, main, task_ids
from scripts.runtime import ROOT, ensure_environment, package_for


@pytest.mark.parametrize('agent', ['codex', 'claude', 'gemini', 'qwen', 'muse'])
def test_agent_presets_cover_both_backends_without_running_models(agent, tmp_path, capsys):
    assert main(['--agent', agent, '--tasks', 'S01,JS_AF01', '--output', str(tmp_path/'runs'), '--dry-run']) == 0
    text = capsys.readouterr().out
    preset = json.loads(PRESETS.read_text())[agent]
    assert preset['model'] in text
    assert '--seed 0' in text and '--seed 5' in text
    assert '--environment unreal-http' in text and '--environment threejs' in text
    assert not (tmp_path/'runs').exists()


def test_task_selection_rejects_duplicates_unknown_and_empty():
    for selection in ['S01,S01', 'UNKNOWN', '']:
        with pytest.raises(ValueError):
            task_ids(selection)


def test_report_export_uses_final_findings_and_cited_frames(tmp_path):
    (tmp_path/'frames').mkdir()
    (tmp_path/'meta.json').write_text(json.dumps({'status':'completed','flags':[
        {'id':'b1','status':'retracted','description':'old','evidence':['a0']},
        {'id':'b2','status':'confirmed','description':'current','evidence':['a2']}], 'done_summary':'done'}))
    (tmp_path/'frames/index.jsonl').write_text('\n'.join(json.dumps({'ref':ref,'file':ref+'.jpg'}) for ref in ['a0','a2']))
    assert export_report(tmp_path) == 'completed'
    assert [f['id'] for f in json.loads((tmp_path/'report.json').read_text())['findings']] == ['b2']
    assert json.loads((tmp_path/'evidence.json').read_text()) == [str(tmp_path/'frames/a2.jpg')]


def test_environment_selection_requires_matching_download_revision(tmp_path):
    package = package_for('JS_AF01')
    assert package['id'] == 'threejs-airfield'
    (tmp_path/package['id']).mkdir()
    (tmp_path/package['id']/'.worldauditbench-release.json').write_text('{"sha256":"old"}')
    with pytest.raises(ValueError, match='--download'):
        ensure_environment('JS_AF01', tmp_path)


def test_viewer_lists_all_tasks_without_environment_or_model():
    result = subprocess.run([sys.executable, str(ROOT/'scripts/view_task.py'), '--list'], capture_output=True,text=True)
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 213


def test_bridge_uses_verified_installed_page(tmp_path):
    from agent.vla.bridge import Bridge
    page = tmp_path/'runtime/scene.html';page.parent.mkdir();page.write_text('<html>scene</html>')
    profiles=tmp_path/'browser-profiles';profiles.mkdir()
    import hashlib
    profile={'browser_root':str(page.parent),'browser_page':page.name,'browser_case':'af01-test','page_sha256':hashlib.sha256(page.read_bytes()).hexdigest()}
    (profiles/'JS_AF01.json').write_text(json.dumps(profile))
    class Page:
        def goto(self,url):self.url=url
        def wait_for_function(self,*args,**kwargs):pass
        def evaluate(self,js):return {} if '__env.meta' in js else None
    br=Bridge(serve_dir=tmp_path,profiles=profiles);br.port=8765;br.page=Page()
    br.open_env('JS_AF01',seed=5,extra={'vclock':1})
    assert '/runtime/scene.html?' in br.page.url and 'bug=af01-test' in br.page.url
    assert 'noui=1' in br.page.url and 'vclock=1' in br.page.url
    page.write_text('changed')
    with pytest.raises(ValueError,match='checksum'):
        br.open_env('JS_AF01')


def test_judge_reads_exported_evidence_without_model_call(tmp_path, monkeypatch):
    from judge import judge
    from PIL import Image
    (tmp_path/'rubric.json').write_text('{"anomaly":"floating chair","expected":"chair rests on floor"}')
    (tmp_path/'report.json').write_text('{"findings":[{"description":"floating chair"}]}')
    Image.new('RGB',(16,16),'blue').save(tmp_path/'frame.png')
    (tmp_path/'evidence.json').write_text('["frame.png"]')
    received=[]
    def score(rubrics, report, images, **kwargs):
        received.extend(images)
        return {'score':1,'reason':'Matched'}
    monkeypatch.setattr(judge,'judge',score)
    assert judge.main(['--rubrics',str(tmp_path/'rubric.json'),'--model-output',str(tmp_path/'report.json'),
                       '--evidence',str(tmp_path/'evidence.json'),'--output',str(tmp_path/'result.json')]) == 0
    assert len(received)==1
    assert json.loads((tmp_path/'result.json').read_text())['score']==1
