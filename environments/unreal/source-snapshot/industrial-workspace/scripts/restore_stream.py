from pathlib import Path
import tarfile,time,hashlib,json,shutil
root=Path('/home/ubuntu/unreal-auditor');work=root/'industrial-workspace';project=work/'project';expected=8718126235
files=list((root/'archives').glob('.industrial-factory-source.tar.gz.*'));assert len(files)==1
class Growing:
 def __init__(self,p):self.f=p.open('rb');self.pos=0;self.digest=hashlib.sha256();self.name=str(p)
 def read(self,n=-1):
  if n<0:n=1024*1024
  while True:
   b=self.f.read(min(n,expected-self.pos))
   if b:self.pos+=len(b);self.digest.update(b);return b
   if self.pos==expected:return b''
   time.sleep(.5)
g=Growing(files[0]);count=0;prev=''
with tarfile.open(fileobj=g,mode='r|gz') as t:
 for m in t:
  prefix='project/FactoryEnvironmentCollect/'
  if not m.isfile() or not m.name.startswith(prefix):continue
  rel=Path(m.name[len(prefix):]);category='/'.join(rel.parts[:2])
  if category!=prev:print('Reading '+category,flush=True);prev=category
  if rel.parts[0] not in ('Content','Config'):continue
  assert '..' not in rel.parts and not rel.is_absolute()
  dest=project/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  with t.extractfile(m) as src,dest.open('wb') as dst:shutil.copyfileobj(src,dst)
  count+=1
while g.read(1024*1024):pass
assert g.digest.hexdigest()=='de067b1124ed703ea5660008f779b8ecf4746e1c9f1d4edc6e3f1bfb30514e60'
(work/'out/source-restoration.json').write_text(json.dumps(dict(source_sha256=g.digest.hexdigest(),files_restored=count,project=str(project)),indent=2))
print('SOURCE RESTORED AND CHECKSUM VERIFIED',flush=True)
