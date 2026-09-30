from pathlib import Path
import hashlib,json,shutil,subprocess
w=Path('/home/ubuntu/unreal-auditor/medieval-workspace');source=w/'source-original';manifest=json.loads((w/'out/source-manifest.json').read_text())
actual={str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
assert actual==set(manifest['files']), {'missing':list(set(manifest['files'])-actual)[:10],'extra':list(actual-set(manifest['files']))[:10]}
for name,expected in manifest['files'].items():
 p=source/name;h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 assert p.stat().st_size==expected['bytes'] and h.hexdigest()==expected['sha256'],name
print('MEDIEVAL_SOURCE_VERIFIED',len(actual),flush=True)
assert not (w/'project/Content').exists(),'Preserve any existing authored project; do not overwrite it.'
subprocess.run(['cp','-a','--reflink=auto',str(source/'Content'),str(w/'project/Content')],check=True)
(w/'out/source-verification.json').write_text(json.dumps({'result':'PASS','files':len(actual),'bytes':sum(v['bytes'] for v in manifest['files'].values()),'source_preserved':str(source),'project':str(w/'project')},indent=2))
