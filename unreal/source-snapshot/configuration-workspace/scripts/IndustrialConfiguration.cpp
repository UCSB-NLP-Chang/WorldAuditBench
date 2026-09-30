#include "IndustrialConfiguration.h"
#include "AuditorPlaytest.h"
#include "Camera/CameraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Particles/ParticleSystemComponent.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "HAL/FileManager.h"
#include "UnrealClient.h"
AIndustrialConfiguration::AIndustrialConfiguration(){PrimaryActorTick.bCanEverTick=true;}
void AIndustrialConfiguration::BeginPlay(){
 Super::BeginPlay();
 const auto* Mode=GetWorld()->GetAuthGameMode();if(Mode)TaskId=UGameplayStatics::ParseOption(Mode->OptionsString,TEXT("Task"));
 Control=FParse::Param(FCommandLine::Get(),TEXT("AuditorControl"));
 Test=(TaskId==TEXT("I19")&&FParse::Param(FCommandLine::Get(),TEXT("AuditorTaskTest")))||FParse::Param(FCommandLine::Get(),TEXT("AuditorConfigurationRobotTest"));
 for(TActorIterator<AActor> I(GetWorld());I;++I){if(I->ActorHasTag(TEXT("configuration_robot")))Robot=*I;if(I->ActorHasTag(TEXT("auditor_actor:ConfigurationTray")))Tray=Cast<AStaticMeshActor>(*I);}
 if(!Robot||!Tray){if(Test)Finish(false,TEXT("Missing configured robot/tray"));return;}
 // Keep the imported skeletal animation/IK; provide a repeatable welding target.
 Robot->SetActorTickEnabled(false);
 TArray<UStaticMeshComponent*> Meshes;Robot->GetComponents(Meshes);for(auto* C:Meshes)if(C->GetName()==TEXT("Effector"))Effector=C;
 Arm=Robot->FindComponentByClass<USkeletalMeshComponent>();Sparks=Robot->FindComponentByClass<UParticleSystemComponent>();
 if(Arm){Arm->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;Arm->bEnableUpdateRateOptimizations=false;}
 WeldPoint=FVector(1905,1887,170);
 if(Tray){Tray->SetMobility(EComponentMobility::Movable);if(TaskId==TEXT("I19")&&!Control)Tray->AddActorWorldOffset(FVector(300,0,0));}
}
void AIndustrialConfiguration::Finish(bool Pass,const FString& Detail){
 UE_LOG(LogTemp,Display,TEXT("AUDITOR_TASK_TEST %s id=%s detail=%s"),Pass?TEXT("PASS"):TEXT("FAIL"),*TaskId,*Detail);Done=true;
 if(FParse::Value(FCommandLine::Get(),TEXT("AuditorCaptureOnTest="),CapturePath)){FScreenshotRequest::RequestScreenshot(CapturePath,false,false);Capturing=true;CaptureAge=Age;return;}
 if(FParse::Param(FCommandLine::Get(),TEXT("AuditorTestExit")))FPlatformMisc::RequestExitWithStatus(false,Pass?0:1);
}
void AIndustrialConfiguration::Tick(float Dt){
 Super::Tick(Dt);Age+=Dt;
 if(Capturing){if(IFileManager::Get().FileExists(*CapturePath))FPlatformMisc::RequestExitWithStatus(false,0);else if(Age-CaptureAge>30)FPlatformMisc::RequestExitWithStatus(false,2);return;}
 if(!Robot||!Tray||!Arm||!Effector)return;
 // A short repeatable seam pass followed by a raised return stroke.
 const float Phase=FMath::Fmod(Age,4.f)/4.f;
 const float X=28.f*FMath::Sin(Phase*2.f*PI);
 const float Lift=Phase>.5f?35.f*FMath::Sin((Phase-.5f)*2.f*PI):0.f;
 const FVector Aim=WeldPoint+FVector(X,0,Lift);
 Effector->SetWorldLocation(Aim);
 if(Sparks){Sparks->SetWorldLocation(Aim);const bool Contact=Phase<.5f&&FMath::Abs(Tray->GetActorLocation().X-1905)<10;Sparks->SetActive(Contact);Sparks->SetVisibility(Contact);}
 if(Test&&!Done){
  if(Age>1.f&&TipBone.IsNone()){
   float Best=MAX_flt;for(int I=0;I<Arm->GetNumBones();++I){const FName Bone=Arm->GetBoneName(I);float D=FVector::Dist(Arm->GetBoneLocation(Bone),Aim);if(D<Best){Best=D;TipBone=Bone;}}
   FirstBonePosition=Arm->GetBoneLocation(TipBone);
   if(auto* P=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0))){P->SetActorLocation(FVector(1600,2260,120));if(P->Controller)P->Controller->SetControlRotation((FVector(2010,1860,150)-P->Camera->GetComponentLocation()).Rotation());}
  }
  if(!TipBone.IsNone()){Motion=FMath::Max(Motion,FVector::Dist(FirstBonePosition,Arm->GetBoneLocation(TipBone)));++Samples;}
  if(Age>10.f){
   const float Offset=FVector::Dist2D(Tray->GetActorLocation(),FVector(1905,1887,0));
   const bool Bug=TaskId==TEXT("I19")&&!Control;
   const bool Pass=Motion>10&&Samples>100&&(Bug?Offset>250:Offset<1);
   Finish(Pass,FString::Printf(TEXT("Actual skeletal bone %s moved %.1f cm across repeated weld cycles; workpiece tray offset %.1f cm; bug=%d"),*TipBone.ToString(),Motion,Offset,Bug));
  }
 }
}
