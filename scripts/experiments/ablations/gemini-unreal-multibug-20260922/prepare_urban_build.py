"""Prepare an isolated opt-in composition binary; never launches model episodes."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,time
B=Path('/mnt/auditor-build/experiment-runs/gemini-unreal-multibug-20260922')
SOURCE=Path('/mnt/auditor-build/urban-ipc-build/project')
WORK=B/'builds/urban';PROJECT=WORK/'project'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not PROJECT.exists(), 'Private source already exists; inspect rather than blindly rebuild'
 original=json.loads(Path('/mnt/auditor-build/urban-ipc-build/build.json').read_text())
 module=SOURCE/'Plugins/AuditorRuntime/Source/AuditorRuntime'
 expected=original['after']
 for rel,h in expected.items():assert sha(module/rel)==h,rel
 PROJECT.mkdir(parents=True)
 for name in ['Source','Config','Plugins']:
  shutil.copytree(SOURCE/name,PROJECT/name,ignore=shutil.ignore_patterns('Intermediate','Binaries','Saved'))
 name='NYC_Building_Volume2';shutil.copy2(SOURCE/(name+'.uproject'),PROJECT)
 dest=PROJECT/'Plugins/AuditorRuntime/Source/AuditorRuntime'
 for part,n in [('Private','AuditorMultibug.cpp'),('Public','AuditorMultibug.h')]:shutil.copyfile(B/'native'/n,dest/part/n)
 remote=dest/'Private/AuditorRemote.cpp';s=remote.read_text();s=s.replace('#include "AuditorRemote.h"','#include "AuditorRemote.h"\n#include "AuditorMultibug.h"',1)
 marker='            Pawn->DisableInput(Controller);';assert s.count(marker)==1
 s=s.replace(marker,'            if (!AuditorMultibug::Prepare(World, AssignedTask, Directory)) return;\n'+marker)
 remote.write_text(s)
 proof={'status':'prepared','time':time.time(),'original_source':str(SOURCE),'original_build_sha256':original['binary_sha256'],'before':expected,'after':{str(p.relative_to(dest)):sha(p) for p in dest.rglob('*') if p.is_file()},'cooked_content_changed':False,'model_launched':False}
 (WORK/'source-proof.json').write_text(json.dumps(proof,indent=2))
 cmd=['/opt/UnrealEngine_5.6/Engine/Build/BatchFiles/Linux/Build.sh',name,'Linux','Development',str(PROJECT/(name+'.uproject')),'-WaitMutex','-MaxParallelActions=8','-NoUBA']
 (WORK/'command.json').write_text(json.dumps(cmd,indent=2))
 with (WORK/'compile.log').open('w') as log:
  result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 proof.update(status='compiled' if result.returncode==0 else 'compile_failed',exit_code=result.returncode,finished_at=time.time())
 if result.returncode==0:
  binary=PROJECT/'Binaries/Linux'/name;proof.update(binary=str(binary),binary_sha256=sha(binary))
 (WORK/'build.json').write_text(json.dumps(proof,indent=2));sys.exit(result.returncode)
if __name__=='__main__':main()
