"""Recook content and rebuild IoStore in private directories, reusing the verified executable."""
from pathlib import Path
import subprocess,shutil,json,hashlib
root=Path('/home/ubuntu/unreal-auditor/rural-workspace');engine=Path('/opt/UnrealEngine_5.6/Engine');project=root/'project/RuralAustralia.uproject';work=root/'out/content-repack-v3';work.mkdir(exist_ok=True)
old=root/'dist/rural-linux-v2';out=root/'dist/rural-linux-v3';assert all(not str(p.get('binary','')).startswith(str(out)+'/') for p in json.loads(Path('/home/ubuntu/unreal-auditor/review-service/state/runtime.json').read_text())['launch_profiles'].values())
# No compilation or shared AutomationTool files are involved in this content-only update.
regions=json.loads((root/'environments/rural-australia/regions.json').read_text())['regions'];cook=work/'Cooked'
args=[str(engine/'Binaries/Linux/UnrealEditor-Cmd'),str(project),'-run=Cook','-TargetPlatform=Linux','-Map='+'+'.join(r['map'] for r in regions),'-OutputDir='+str(cook),'-unversioned','-unattended','-nop4','-stdout','-UTF8Output','-NoLogTimes','-abslog='+str(work/'cook-engine.log')]
with (work/'cook.log').open('w') as f:subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,check=True)
# OutputDir is the platform sandbox root; locate the manifest rather than assume an extra Linux segment.
manifest=next(cook.rglob('packagestore.manifest'));cooked=manifest.parents[2];meta=manifest.parent
if not (meta/'Crypto.json').exists():shutil.copy2(root/'project/Saved/Cooked/Linux/RuralAustralia/Metadata/Crypto.json',meta/'Crypto.json')
shutil.copytree(old,out,dirs_exist_ok=True)
paks=out/'Linux/RuralAustralia/Content/Paks'
for p in list(paks.glob('*.utoc'))+list(paks.glob('*.ucas')):p.unlink()
response=work/'IoStoreResponse.txt';files=sorted(p for p in cooked.rglob('*') if p.is_file() and p.suffix in {'.uasset','.umap','.uexp','.ubulk','.uptnl','.ushaderbytecode'})
assert len(files)>1800
response.write_text('\n'.join('"'+str(p)+'" "../../../'+p.relative_to(cooked).as_posix()+'" -compress' for p in files)+'\n')
commands=work/'IoStoreCommands.txt';commands.write_text('-Output="'+str(paks/'RuralAustralia-Linux.utoc')+'" -ContainerName=RuralAustralia -ResponseFile="'+str(response)+'"\n')
args=[str(engine/'Binaries/Linux/UnrealPak'),str(project),'-CreateGlobalContainer='+str(paks/'global.utoc'),'-PackageStoreManifest='+str(manifest),'-CookedDirectory='+str(cooked),'-Commands='+str(commands),'-ScriptObjects='+str(meta/'scriptobjects.bin'),'-compressionformats=Oodle','-compresslevel=4','-compressmethod=Kraken','-cryptokeys='+str(meta/'Crypto.json'),'-compressionMinBytesSaved=1024','-compressionMinPercentSaved=5','-WriteBackMetadataToAssetRegistry=Disabled','-unattended','-nopak','-abslog='+str(work/'iostore-engine.log')]
with (work/'iostore.log').open('w') as f:subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,check=True)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
binary=out/'Linux/RuralAustralia/Binaries/Linux/RuralAustralia';sha=digest(binary);assert sha==json.loads((old/'build-provenance.json').read_text())['binary_sha256']
proof=dict(engine='5.6.1',project=str(project),binary_sha256=sha,maps=[r['map'] for r in regions],method='private content cook and IoStore rebuild; unchanged v2 executable',source_build=str(old),containers={p.name:digest(p) for p in paks.iterdir() if p.is_file()},cook_files=len(files))
(out/'build-provenance.json').write_text(json.dumps(proof,indent=2))
for n in ['tasks.json','regions.json']:shutil.copy2(root/'environments/rural-australia'/n,out/n)
print('RURAL_CONTENT_REPACK_PASS',sha,flush=True)
