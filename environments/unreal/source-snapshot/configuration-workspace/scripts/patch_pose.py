from pathlib import Path
import json,shutil
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');cfg=json.loads((w/'projects.json').read_text());report=[]
def change(p,s):
 backup=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');backup.parent.mkdir(parents=True,exist_ok=True)
 if not backup.exists():shutil.copy2(p,backup)
 p.write_text(s);report.append(str(p))
for family in ['subway','ancient']:
 root=Path(cfg[family]['project']).parent/'Plugins/AuditorRuntime/Source/AuditorRuntime/Private';p=root/'AuditorTasks.cpp';s=p.read_text()
 assert 'ConfigurationPose.inl' not in s
 s=s.replace('AAuditorTasks::AAuditorTasks()', '#include "ConfigurationPose.inl"\n\nAAuditorTasks::AAuditorTasks()',1)
 needle='    if (Kind == TEXT("offset"))';assert s.count(needle)>=1
 s=s.replace(needle,'    if (Kind == TEXT("configuration_pose")) ApplyConfigurationPose(Target,Spec);\n    else if (Kind == TEXT("offset"))',1)
 # Insert a dedicated test before the existing tilt branch in TestStep.
 start=s.index('void AAuditorTasks::TestStep');a=s[:start];b=s[start:];needle='    else if (Kind == TEXT("tilt"))';assert b.count(needle)==1
 b=b.replace(needle,'    else if (Kind == TEXT("configuration_pose")) { FString Detail;const bool Pass=CheckConfigurationPose(Target,Original,Spec,Detail);FinishTest(Pass,Detail); }\n'+needle,1)
 change(p,a+b);shutil.copy2(w/'scripts/ConfigurationPose.inl',root/'ConfigurationPose.inl')
# Indoor has its own scenario dispatcher and control/bug QA.
root=Path(cfg['indoor']['project']).parent/'Plugins/AuditorRuntime/Source/AuditorRuntime/Private';p=root/'ResidentialScenario.cpp';s=p.read_text();assert 'ConfigurationPose.inl' not in s
s=s.replace('AResidentialScenario::AResidentialScenario()', '#define VectorField V\n#include "ConfigurationPose.inl"\n#undef VectorField\n\nAResidentialScenario::AResidentialScenario()',1)
needle='        if(Kind==TEXT("floating")';assert s.count(needle)==1
s=s.replace(needle,'        if(Kind==TEXT("configuration_pose"))ApplyConfigurationPose(Target,Spec);\n        else if(Kind==TEXT("floating")',1)
needle='    if(Kind==TEXT("layout")){';assert s.count(needle)==1
s=s.replace(needle,'    if(Kind==TEXT("configuration_pose")){FString Detail;const bool Pass=CheckConfigurationPose(Target,Original,Spec,Detail);Finish(Pass,Detail);return;}\n'+needle,1)
change(p,s);shutil.copy2(w/'scripts/ConfigurationPose.inl',root/'ConfigurationPose.inl')
(w/'out/pose-source-changes.json').write_text(json.dumps(report,indent=2));print('POSE_SOURCE_UPDATED',len(report))
