from pathlib import Path
import shutil
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');root=Path('/home/ubuntu/unreal-auditor/industrial-workspace/project/Plugins/AuditorRuntime/Source/AuditorRuntime')
for name,folder in [('IndustrialConfiguration.h','Public'),('IndustrialConfiguration.cpp','Private')]:
 p=root/folder/name;assert not p.exists();shutil.copy2(w/'scripts'/name,p)
p=root/'Private/AuditorTasks.cpp';b=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b);s=p.read_text();needle='void AAuditorTasks::TestStep(float DeltaSeconds)';i=s.find(needle)
if i<0:
 import re
 m=re.search(r'void AAuditorTasks::TestStep\([^)]*\)\s*\{',s);assert m;s=s[:m.end()]+'\n    if(ActiveId==TEXT("I19"))return; // AIndustrialConfiguration verifies actual skeletal motion and target alignment.\n'+s[m.end():]
else:
 i=s.index('{',i)+1;s=s[:i]+'\n    if(ActiveId==TEXT("I19"))return; // Separate actual skeletal-motion verification.\n'+s[i:]
p.write_text(s);print('INDUSTRIAL_CONFIGURATION_CODE_INSTALLED')
