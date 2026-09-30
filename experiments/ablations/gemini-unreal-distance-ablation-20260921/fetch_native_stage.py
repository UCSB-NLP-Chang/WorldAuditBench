from pathlib import Path
import json,subprocess,sys,io,tarfile
B=Path(__file__).resolve().parent;ROOT=B.parents[3];cfg=json.loads((ROOT/'out/native-agents/aws-connection.json').read_text());stage=sys.argv[1];assert stage in ['rendered-framing-qa','rendered-trigger-qa','rendered-final-probe-qa','rendered-resolution-probe-qa']
known=[str(p.parent.relative_to(B)) for p in (B/stage).glob('*/*/result.json')]
code='''from pathlib import Path
import io,tarfile,sys
b=Path('/mnt/auditor-build/experiment-runs/gemini-unreal-distance-ablation-20260921');buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as tar:
 for p in (b/STAGE).glob('*/*/result.json'):
  if str(p.parent.relative_to(b)) in KNOWN:continue
  for f in p.parent.iterdir():
   if f.is_file() and (f.suffix=='.json' or f.suffix=='.png' and not f.name.startswith('frame_') and f.name!='observation.png'):tar.add(f,arcname=str(f.relative_to(b)))
sys.stdout.buffer.write(buf.getvalue())
'''.replace('STAGE',repr(stage)).replace('KNOWN',repr(known))
r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i',cfg['identity'],cfg['host'],'python3.12 -'],input=code.encode(),capture_output=True,timeout=180);assert r.returncode==0,r.stderr.decode()[-500:]
with tarfile.open(fileobj=io.BytesIO(r.stdout),mode='r:gz') as tar:tar.extractall(B,filter='data')
print(stage,len(list((B/stage).glob('*/*/result.json'))),'local completed episodes')
