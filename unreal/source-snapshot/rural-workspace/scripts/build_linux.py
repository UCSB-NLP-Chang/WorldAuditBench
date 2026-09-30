from pathlib import Path
import subprocess,json,hashlib,shutil,os
root=Path(__file__).resolve().parents[1];project=root/'project/RuralAustralia.uproject';engine=Path('/opt/UnrealEngine_5.6/Engine');out=root/'dist/rural-linux-v3';logs=root/'out/build';logs.mkdir(parents=True,exist_ok=True)
assert shutil.disk_usage(root).free>40*1024**3
for p in json.loads(Path('/home/ubuntu/unreal-auditor/review-service/state/runtime.json').read_text()).get('launch_profiles',{}).values():
 assert not str(p.get('binary','')).startswith(str(out)+'/'),'Output already published'
regions=json.loads((root/'environments/rural-australia/regions.json').read_text())['regions']
config=project.parent/'Config/DefaultEngine.ini';s=config.read_text();s=s.replace('/Game/ThirdPerson/Maps/ThirdPersonMap','/Game/Auditor/RuralAustralia/RoadBend').replace('/Engine/Maps/Templates/OpenWorld','/Game/Auditor/RuralAustralia/RoadBend');config.write_text(s)
args=[str(engine/'Build/BatchFiles/RunUAT.sh'),'-WaitForUATMutex','BuildCookRun','-project='+str(project),'-platform=Linux','-clientconfig=Development','-build','-cook','-stage','-pak','-package','-archive','-archivedirectory='+str(out),'-map='+'+'.join(r['map'] for r in regions),'-nop4','-utf8output','-unattended','-UbtArgs=-MaxParallelActions=8 -NoUBA -WaitMutex']
with (logs/'package.log').open('w') as f:subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,check=True)
binary=out/'Linux/RuralAustralia/Binaries/Linux/RuralAustralia';digest=hashlib.sha256()
with binary.open('rb') as f:
 for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)
h=digest.hexdigest()
(out/'build-provenance.json').write_text(json.dumps(dict(engine='5.6.1',project=str(project),binary_sha256=h,maps=[r['map'] for r in regions]),indent=2))
for n in ['regions.json','tasks.json']:shutil.copy2(root/'environments/rural-australia'/n,out/n)
print('RURAL_LINUX_BUILD_PASS',h,flush=True)
