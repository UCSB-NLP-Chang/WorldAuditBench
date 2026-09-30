from pathlib import Path
import json,subprocess
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');build=json.loads((w/'out/build-urban.json').read_text());author=json.loads((w/'out/author-urban.json').read_text());out=w/'out/render-urban';out.mkdir(exist_ok=True);results=[]
for m in author['maps']:
 name=m['variant'].lower();dest=out/name;dest.mkdir(exist_ok=True);spec={'output':str(dest),'task':'U046','state':False,'steps':[{'name':'mailbox-front','position':[1540,410,201.219],'aim':[1659,717,167]},{'name':'mailbox-side','position':[1880,490,201.219],'aim':[1659,717,167]}]};p=dest/'probe.json';p.write_text(json.dumps(spec))
 with (dest/'game.log').open('w') as log:
  code=subprocess.run([build['binary'],m['map'],'-vulkan','-sm6','-RenderOffscreen','-ResX=1280','-ResY=800','-ForceRes','-AuditorSkipSceneMenu','-AuditorRemoteInput','-unattended','-nosound','-ExecCmds=t.MaxFPS 30,DisableAllScreenMessages','-AuditorMigrationProbe='+str(p)],stdout=log,stderr=subprocess.STDOUT,timeout=120).returncode
 result={'variant':name,'ok':code==0 and json.loads((dest/'result.json').read_text())['passed'],'rendered_views':2};results.append(result);print(json.dumps(result),flush=True)
# The unchanged real character must still traverse the canonical new case map and respect its scene bounds.
for kind in ['Traversal','Boundary']:
 with (out/(kind+'.log')).open('w') as log:
  code=subprocess.run([build['binary'],next(m['map'] for m in author['maps'] if m['variant']=='Bug'),'-nullrhi','-nosound','-unattended','-AuditorSkipSceneMenu','-AuditorRemoteInput','-AuditorTestExit','-ExecCmds=t.MaxFPS 30','-Auditor'+kind+'Test'],stdout=log,stderr=subprocess.STDOUT,timeout=100).returncode
 text=(out/(kind+'.log')).read_text(errors='replace');results.append({'kind':kind,'ok':code==0 and 'AUDITOR_'+kind.upper()+'_TEST PASS' in text});print(json.dumps(results[-1]),flush=True)
(out/'report.json').write_text(json.dumps(results,indent=2));assert all(r['ok'] for r in results)
