from pathlib import Path
import subprocess,json,hashlib,shutil,os
root=Path(__file__).resolve().parents[1];project=root/'project/AncientChineseCity.uproject';engine=Path('/opt/UnrealEngine_5.6/Engine');output=Path(os.getenv('ANCIENT_BUILD_OUTPUT',str(root/'dist/ancient-linux')));logs=root/'out/build';logs.mkdir(parents=True,exist_ok=True)
assert shutil.disk_usage(root).free>40*1024**3
# Never replace an executable currently referenced by the live review service.
live=Path('/home/ubuntu/unreal-auditor/review-service/state/runtime.json')
if live.exists():
 target=output/'Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity'
 for profile in json.loads(live.read_text()).get('launch_profiles',{}).values():
  if Path(profile.get('binary','/nonexistent')).resolve()==target.resolve():
   raise SystemExit('Choose a fresh ANCIENT_BUILD_OUTPUT; this output is published.')
regions=json.loads((root/'environments/ancient-chinese-city/regions.json').read_text())['regions']
for reg in regions:assert (project.parent/'Content'/(reg['map'][6:]+'.umap')).exists()
args=[str(engine/'Build/BatchFiles/RunUAT.sh'),'BuildCookRun','-project='+str(project),'-platform=Linux','-clientconfig=Development','-build',('-skipcook' if os.getenv('ANCIENT_SKIP_COOK') else '-cook'),'-stage','-pak','-package','-archive','-archivedirectory='+str(output),'-map='+'+'.join(r['map'] for r in regions),'-nop4','-utf8output','-unattended','-UbtArgs=-MaxParallelActions=8 -NoUBA -WaitMutex']
with (logs/'package.log').open('w') as log:subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
binary=output/'Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity';h=hashlib.sha256()
with binary.open('rb') as f:
 for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
(output/'build-provenance.json').write_text(json.dumps({'engine':'5.6.1','project':str(project),'binary_sha256':h.hexdigest(),'maps':[r['map'] for r in regions]},indent=2))
for name in ['regions.json','tasks.json','scene-descriptions.json','streaming-settings.json','npc-layout.json']:shutil.copy2(root/'environments/ancient-chinese-city'/name,output/name)
print('ANCIENT_LINUX_BUILD_PASS',h.hexdigest(),flush=True)
