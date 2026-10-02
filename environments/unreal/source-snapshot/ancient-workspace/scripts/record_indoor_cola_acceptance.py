from pathlib import Path
import json
from prepare_review import digest
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');o=r/'out/indoor-cola-v3'
for name,count in [('tests',34),('reuse',24),('render',5)]:
 rows=json.loads((o/name/'report.json').read_text());assert len(rows)==count and all(x['ok'] for x in rows),name
assert json.loads((o/'route.json').read_text())['result']=='PASS'
assert json.loads((o/'visual-review.json').read_text())['result']=='PASS'
b=r/'dist/ancient-indoor-cola-20260913-v3/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity';paks=b.parents[2]/'Content/Paks'
files=[b,*paks.glob('*'),*[r/'project/Content/Auditor/AncientCity'/(n+'.umap') for n in ['Market','TeaHouse','Courtyard']],*[r/'environments/ancient-chinese-city'/n for n in ['tasks.json','scene-descriptions.json','concise-rubrics.json','npc-layout.json']],o/'authored.json',o/'route.json',o/'visual-review.json',*[o/n/'report.json' for n in ['tests','reuse','render']]]
files += [r/'source-additions/indoor-cola-v3/manifest.json',r/'scripts/author_indoor_cola.py',r/'scripts/author_ac.py',r/'scripts/import_indoor_cola.py']
files += [p for p in (r/'project/Plugins/AuditorRuntime/Source').rglob('*') if p.suffix in ('.cpp','.h','.inl')]
proof=dict(result='PASS',release_name='ancient-indoor-cola-20260913-v3',binary=str(b),binary_sha256=digest(b),game_args=json.loads((r/'environments/ancient-chinese-city/streaming-settings.json').read_text())['game_args'],native_tests_passed=34,restoration_cycles_passed=24,rendered_views=5,changed_cases=['A21','A24'],artifact_sha256={str(p.relative_to(r)):digest(p) for p in files if p.is_file()})
(o/'acceptance.json').write_text(json.dumps(proof,indent=2));print('AC_ACCEPTANCE_PASS')
