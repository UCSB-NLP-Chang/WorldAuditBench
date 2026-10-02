"""Restore only the industrial Content and Config from the checksum-verified archive."""
from pathlib import Path
import tarfile,hashlib,json
root=Path('/home/ubuntu/unreal-auditor');archive=root/'archives/industrial-factory-source.tar.gz';work=root/'industrial-workspace';project=work/'project'
h=hashlib.sha256()
with archive.open('rb') as f:
 for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
assert h.hexdigest()=='de067b1124ed703ea5660008f779b8ecf4746e1c9f1d4edc6e3f1bfb30514e60'
count=0
with tarfile.open(archive,'r|gz') as t:
 for m in t:
  if not m.isfile():continue
  prefix='project/FactoryEnvironmentCollect/'
  if not m.name.startswith(prefix):continue
  rel=Path(m.name[len(prefix):])
  if rel.parts[0] not in ('Content','Config'):continue
  assert '..' not in rel.parts and not rel.is_absolute()
  dest=project/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  with t.extractfile(m) as src, dest.open('wb') as dst:
   import shutil
   shutil.copyfileobj(src,dst)
  count+=1
# The baseline uses native actors, not the UE4 PhysX vehicle code.
for f in (project/'Config').glob('*.ini'):
 b=f.read_bytes();text=b.decode('utf-16') if b.startswith((b'\xff\xfe',b'\xfe\xff')) else b.decode('utf-8-sig')
 f.write_text(text)
f=project/'Config/DefaultEngine.ini';s=f.read_text();s+='\n[/Script/LinuxTargetPlatform.LinuxTargetSettings]\n!TargetedRHIs=ClearArray\n+TargetedRHIs=SF_VULKAN_SM5\n\n[SystemSettings]\nr.MotionBlurQuality=0\nr.Streaming.PoolSize=2048\nt.MaxFPS=30\n';f.write_text(s)
(work/'out/source-restoration.json').write_text(json.dumps(dict(source_sha256=h.hexdigest(),files_restored=count,project=str(project)),indent=2))
print('Verified and restored',count,'files',flush=True)
