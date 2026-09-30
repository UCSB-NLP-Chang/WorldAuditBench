from pathlib import Path
import time,json,shutil
r=Path('/home/ubuntu/unreal-auditor');spec=r/'industrial-workspace/out/upload-parts.json'
while not spec.exists():time.sleep(.5)
s=json.loads(spec.read_text());dest=r/'archives/industrial-factory-source.tar.gz';assert dest.stat().st_size==s['start']
for p in s['parts']:
 src=Path(p['path']);deadline=time.monotonic()+1800
 while not src.exists():
  assert time.monotonic()<deadline,'Range upload timed out'
  time.sleep(.5)
 assert src.stat().st_size==p['count'] and dest.stat().st_size==p['begin']
 with src.open('rb') as source,dest.open('ab') as target:shutil.copyfileobj(source,target,4*1024*1024)
 print('Appended range',p['index'],flush=True)
assert dest.stat().st_size==s['size'];print('Upload assembly complete',flush=True)
