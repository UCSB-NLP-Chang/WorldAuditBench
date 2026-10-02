"""Reconstruct isolated family candidates. A-only equivalence remains a hard QA gate."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,subprocess,time
B=Path('/mnt/auditor-build/experiment-runs/gemini-unreal-multibug-20260922')
ROOT=Path('/home/ec2-user/unreal-source-recovery-20260919/lambda-source-20260914/lambda')
FAMILIES={'subway':('projects/Subway','Subway'),'indoor':('indoor-workspace/project','AtmosphericResidentialHou'),'industrial':('industrial-workspace/project','FactoryEnvironmentCollect'),'ancient':('ancient-workspace/project','AncientChineseCity'),'medieval':('medieval-workspace/project','MedievalVillage'),'rural':('rural-workspace/project','RuralAustralia')}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
def prepare(family,relative,name):
 source=ROOT/relative;work=B/'builds'/family;project=work/'project';assert not project.exists()
 project.mkdir(parents=True)
 for n in ['Source','Config','Plugins']:
  shutil.copytree(source/n,project/n,ignore=shutil.ignore_patterns('Intermediate','Binaries','Saved'))
 shutil.copy2(source/(name+'.uproject'),project)
 module=project/'Plugins/AuditorRuntime/Source/AuditorRuntime'
 before={str(p.relative_to(module)):sha(p) for p in module.rglob('*') if p.is_file()}
 spec=importlib.util.spec_from_file_location('exploration_install',B/'exploration/install_native.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 helper.install(module,work/'before-exploration')
 if family=='indoor':
  after=Path('/home/ec2-user/unreal-review-releases/unreal-area-3x-20260918/source-after')
  for rel in ['Private/AuditorPlaytest.cpp','Public/AuditorPlaytest.h','Private/AuditorExploration.cpp']:shutil.copyfile(after/rel,module/rel)
 for part,n in [('Private','AuditorMultibug.cpp'),('Public','AuditorMultibug.h')]:shutil.copyfile(B/'native'/n,module/part/n)
 path=module/'Private/AuditorRemote.cpp';s=path.read_text()
 s=s.replace('#include "AuditorRemote.h"','#include "AuditorRemote.h"\n#include "AuditorExploration.h"\n#include "AuditorMultibug.h"',1)
 needle='    if (!Pawn || !Controller) return;';assert s.count(needle)==1
 s=s.replace(needle,needle+'\n    if (AuditorExploration::Pending(World)) return;')
 needle='            Pawn->DisableInput(Controller);';assert s.count(needle)==1
 s=s.replace(needle,'            FString CompositionTask;\n            FParse::Value(FCommandLine::Get(),TEXT("AuditorExplorationTask="),CompositionTask);\n            if (!AuditorMultibug::Prepare(World, CompositionTask, Directory)) return;\n'+needle)
 path.write_text(s)
 proof={'status':'source_prepared_needs_equivalence_qa','source':str(source),'before':before,'after':{str(p.relative_to(module)):sha(p) for p in module.rglob('*') if p.is_file()},'cooked_content_changed':False,'historical_source_requires_reference_comparison':True,'models_started':0}
 write(work/'source-proof.json',proof)
 return work,project,name,proof

def main():
 prepared=[]
 for family,(relative,name) in FAMILIES.items():prepared.append((family,*prepare(family,relative,name)))
 # Keep all builds journaled and sequential. Never overwrite an earlier build attempt.
 while not (B/'builds/urban/build.json').exists():time.sleep(10)
 results={}
 for family,work,project,name,proof in prepared:
  cmd=['/opt/UnrealEngine_5.6/Engine/Build/BatchFiles/Linux/Build.sh',name,'Linux','Development',str(project/(name+'.uproject')),'-WaitMutex','-MaxParallelActions=16','-NoUBA']
  write(work/'command.json',cmd);write(B/'family-build-status.json',{'active':family,'completed':results,'models_started':0,'time':time.time()})
  with (work/'compile.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
  proof.update(status='compiled' if r.returncode==0 else 'compile_failed',exit_code=r.returncode,finished_at=time.time())
  if r.returncode==0:
   binary=project/'Binaries/Linux'/name;proof.update(binary=str(binary),binary_sha256=sha(binary))
  write(work/'build.json',proof);results[family]=proof['status']
 write(B/'family-build-status.json',{'active':None,'completed':results,'models_started':0,'time':time.time()})
if __name__=='__main__':main()
