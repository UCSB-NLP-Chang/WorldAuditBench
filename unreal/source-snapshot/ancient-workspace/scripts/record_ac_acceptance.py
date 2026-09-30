from pathlib import Path
import json
from prepare_review import digest
r=Path('/home/ubuntu/unreal-auditor/ancient-workspace');o=r/'out/ac-v2'
for name,count in [('tests',34),('reuse',24),('render',3)]:
 rows=json.loads((o/name/'report.json').read_text());assert len(rows)==count and all(x['ok'] for x in rows),name
assert json.loads((o/'route.json').read_text())['result']=='PASS'
assert json.loads((o/'visual-review.json').read_text())['result']=='PASS'
b=r/'dist/ancient-ac-20260913-v2/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity';paks=b.parents[2]/'Content/Paks'
files=[b,*paks.glob('*'),*[r/'project/Content/Auditor/AncientCity'/(n+'.umap') for n in ['Market','TeaHouse','Courtyard']],*[r/'environments/ancient-chinese-city'/n for n in ['tasks.json','scene-descriptions.json','concise-rubrics.json','npc-layout.json']],o/'authored.json',o/'route.json',o/'visual-review.json',*[o/n/'report.json' for n in ['tests','reuse','render']]]
files += [p for p in (r/'project/Plugins/AuditorRuntime/Source').rglob('*') if p.suffix in ('.cpp','.h','.inl')]
proof=dict(result='PASS',release_name='ancient-ac-20260913-v2',binary=str(b),binary_sha256=digest(b),game_args=json.loads((r/'environments/ancient-chinese-city/streaming-settings.json').read_text())['game_args'],native_tests_passed=34,restoration_cycles_passed=24,rendered_views=3,changed_cases=['A24'],artifact_sha256={str(p.relative_to(r)):digest(p) for p in files if p.is_file()})
(o/'acceptance.json').write_text(json.dumps(proof,indent=2));print('AC_ACCEPTANCE_PASS')
