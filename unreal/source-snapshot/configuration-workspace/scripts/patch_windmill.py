from pathlib import Path
import json,shutil
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');root=Path('/home/ubuntu/unreal-auditor/medieval-workspace');p=root/'project/Plugins/AuditorRuntime/Source/AuditorRuntime/Private/MedievalInteractions.cpp';s=p.read_text();assert 'CONFIGURATION_WINDMILL' not in s
b=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b)
needle=' CommonTest=FParse::Param';assert s.count(needle)==1
s=s.replace(needle,''' if(TaskId==TEXT("MV17")&&Windmill&&Rotor&&!FParse::Param(FCommandLine::Get(),TEXT("AuditorControl"))){
  // Rotate the existing shaft and blades together; mount the shaft into the roof peak.
  Windmill->SetActorRotation(Windmill->GetActorQuat()*FRotator(90,0,0).Quaternion());
  Windmill->SetActorLocation(FVector(40471.2,29492.86,-2388));
  UE_LOG(LogTemp,Display,TEXT("CONFIGURATION_WINDMILL horizontal rooftop mounting"));
 }
'''+needle,1)
s=s.replace('return TaskId==TEXT("MV06")||TaskId==TEXT("MV14");','return TaskId==TEXT("MV06")||TaskId==TEXT("MV14")||TaskId==TEXT("MV17");')
needle=' if(Windmill&&(TaskId==TEXT("MV14")';assert s.count(needle)==1
s=s.replace(needle,''' if(TaskId==TEXT("MV17")){
  if(!Windmill||!Rotor||!Rotor->UpdatedComponent){Finish(false,TEXT("Missing authored windmill rotor"));return;}
  const bool Control=FParse::Param(FCommandLine::Get(),TEXT("AuditorControl"));
  if(Phase==0){View(P->Region->SpawnLocation,Windmill->GetActorLocation());WindmillSample=Rotor->UpdatedComponent->GetComponentQuat();Phase=1;PhaseAge=0;}
  else if(Phase==1&&PhaseAge>1.f){
   FQuat Delta=Rotor->UpdatedComponent->GetComponentQuat()*WindmillSample.Inverse();Delta.Normalize();if(Delta.W<0)Delta=Delta*-1.f;
   FVector Axis;float Angle;Delta.ToAxisAndAngle(Axis,Angle);
   const bool Motion=FMath::Abs(Angle)>.1f;
   const bool Direction=Control?FMath::Abs(Axis.Z)<.05f:FMath::Abs(Axis.Z)>.99f;
   bool Support=true;
   if(!Control){FHitResult H;FCollisionQueryParams Q(SCENE_QUERY_STAT(ConfigurationWindmillSupport),true,Windmill);const FVector Top(40471.2,29492.86,-2300);GetWorld()->LineTraceSingleByChannel(H,Top,Top-FVector(0,0,160),ECC_Visibility,Q);Support=H.bBlockingHit;}
   Finish(Motion&&Direction&&Support,FString::Printf(TEXT("Measured rotating blades: axis=%s angle=%.2f; roof support=%d control=%d"),*Axis.ToString(),Angle,Support,Control));
  }
  return;
 }
'''+needle,1)
p.write_text(s)
p=root/'environments/medieval-village/tasks.json';b=w/'backups'/p.relative_to('/home/ubuntu/unreal-auditor');b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b);d=json.loads(p.read_text());t=next(t for t in d['tasks'] if t['id']=='MV17')
for k in ['offset','position','review_aim']:t.pop(k,None)
t.update(kind='windmill_configuration',target='',subcategory='S2',title='Windmill rotor mounted horizontally',review_aim=[40471,29493,-2200]);t['rubrics_i18n']={'zh':{'criteria':'风车叶轮水平安装在塔顶，像旋翼一样在水平面内转动。','expected':'正常情况下，该风车的叶轮应安装在塔身侧面，在竖直面内转动。','steps':'从庭院观察风车塔顶和叶轮，连续观看转动方向，并与正常对照比较。'},'en':{'criteria':'The windmill rotor is mounted horizontally on the roof and spins like a helicopter rotor.','expected':'This windmill should have its rotor mounted on the side of the tower, turning in a vertical plane.','steps':'Observe the roof and blades from the courtyard, watching their rotation and comparing with the baseline.'}}
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print('WINDMILL_CONFIGURATION_PATCHED')
