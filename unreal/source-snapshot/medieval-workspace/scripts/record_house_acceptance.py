"""Record final binary, package, catalog and QA hashes after visual inspection."""
from pathlib import Path
import json,shutil
from prepare_review import digest
r=Path('/home/ubuntu/unreal-auditor/medieval-workspace');o=r/'out/house-v3'
for name,count in [('tests-final',27),('reuse-final',21),('render-final',6)]:
 rows=json.loads((o/name/'report.json').read_text());assert len(rows)==count and all(x['ok'] for x in rows),name
assert json.loads((r/'out/route-verification.json').read_text())['result']=='PASS'
assert json.loads((o/'visual-review.json').read_text())['result']=='PASS'
b=r/'dist/medieval-linux-v3/Linux/MedievalVillage/Binaries/Linux/MedievalVillage';pak=b.parents[2]/'Content/Paks';assert list(pak.glob('*.pak'))
shutil.copy2(r/'source-additions/fab-props-20260912/ATTRIBUTION.md',b.parents[3]/'Medieval-Prop-Credits.md')
files=[*pak.glob('*'),*[r/'project/Content/Auditor/MedievalVillage'/(n+'.umap') for n in ('Market','Windmill')],r/'environments/medieval-village/tasks.json',r/'environments/medieval-village/scene-descriptions.json',r/'out/route-verification.json',o/'visual-review.json',*[o/n/'report.json' for n in ('tests-final','reuse-final','render-final')]]
proof=dict(result='PASS',release_name='medieval-house-20260912-v3',binary=str(b),binary_sha256=digest(b),game_args=['-vulkan','-sm6','-PixelStreamingWebRTCMaxFps=30','-ExecCmds=t.MaxFPS 30'],native_tests_passed=27,restoration_cycles_passed=21,rendered_views=6,human_acceptance='pending',artifact_sha256={str(p.relative_to(r)):digest(p) for p in files if p.is_file()})
(o/'acceptance.json').write_text(json.dumps(proof,indent=2));print('HOUSE_ACCEPTANCE_PASS')
