"""Bind native, restoration, render and visual checks to immutable release artifacts."""
from pathlib import Path
import json
from prepare_review import digest
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');o=r/'out/era-v1'
for name,count in [('tests-final',34),('reuse-final',24),('render-final',11)]:
 rows=json.loads((o/name/'report.json').read_text());assert len(rows)==count and all(x['ok'] for x in rows),name
assert json.loads((o/'route.json').read_text())['result']=='PASS'
assert json.loads((o/'visual-review.json').read_text())['result']=='PASS'
b=r/'dist/ancient-era-20260913-v1/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity';pak=b.parents[2]/'Content/Paks';assert list(pak.glob('*.pak'))
files=[b,*pak.glob('*'),*[r/'project/Content/Auditor/AncientCity'/(n+'.umap') for n in ['Market','TeaHouse','Courtyard']],*[r/'environments/ancient-chinese-city'/n for n in ['tasks.json','scene-descriptions.json','concise-rubrics.json','npc-layout.json']],r/'project/Plugins/AuditorRuntime/Source/AuditorRuntime/Private/AuditorTasks.cpp',o/'route.json',o/'visual-review.json',*[o/n/'report.json' for n in ['tests-final','reuse-final','render-final']]]
proof=dict(result='PASS',release_name='ancient-era-20260913-v1',binary=str(b),binary_sha256=digest(b),game_args=json.loads((r/'environments/ancient-chinese-city/streaming-settings.json').read_text())['game_args'],native_tests_passed=34,restoration_cycles_passed=24,rendered_views=11,added_cases=['A21','A22','A23','A24'],artifact_sha256={str(p.relative_to(r)):digest(p) for p in files if p.is_file()})
(o/'acceptance.json').write_text(json.dumps(proof,indent=2));print('ERA_ACCEPTANCE_PASS',flush=True)
