#include "IndustrialOperational.h"
#include "AuditorPlaytest.h"
#include "Camera/CameraComponent.h"
#include "Components/LightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "HAL/FileManager.h"
#include "UnrealClient.h"
AIndustrialOperational::AIndustrialOperational(){PrimaryActorTick.bCanEverTick=true;}
void AIndustrialOperational::BeginPlay(){
 Super::BeginPlay();
 const auto* Mode=GetWorld()->GetAuthGameMode();if(Mode)CaseId=UGameplayStatics::ParseOption(Mode->OptionsString,TEXT("Task"));
 Bug=(CaseId==TEXT("I20")||CaseId==TEXT("I21"))&&!FParse::Param(FCommandLine::Get(),TEXT("AuditorControl"));
 if(CaseId!=TEXT("I20")&&CaseId!=TEXT("I21"))FParse::Value(FCommandLine::Get(),TEXT("AuditorOperationalCase="),CaseId);
 if(CaseId!=TEXT("I20")&&CaseId!=TEXT("I21")){SetActorTickEnabled(false);return;}
 Testing=FParse::Param(FCommandLine::Get(),TEXT("AuditorTaskTest"))||FParse::Param(FCommandLine::Get(),TEXT("AuditorOperationalTest"));
 FParse::Value(FCommandLine::Get(),TEXT("AuditorOperationalCapturePrefix="),CapturePrefix);
 const bool Lamp=CaseId==TEXT("I20");
 const FName TargetTag(Lamp?TEXT("auditor_actor:SM_LampSet_49"):TEXT("auditor_actor:SM_DeskControl_4"));
 for(TActorIterator<AActor> I(GetWorld());I;++I){
  if(I->ActorHasTag(TargetTag))Target=Cast<AStaticMeshActor>(*I);
  if(I->ActorHasTag(TEXT("operational_light")))Light=I->FindComponentByClass<ULightComponent>();
 }
 if(!Target||!OffMaterial||(Lamp&&!Light)){Finish(false,TEXT("Missing authored operational target"));return;}
 Original=Target->GetActorTransform();
 auto* Mesh=Target->GetStaticMeshComponent();
 for(int i=0;i<Mesh->GetNumMaterials();++i)OriginalMaterials.Add(Mesh->GetMaterial(i));
 Panel=Mesh->CreateDynamicMaterialInstance(Lamp?0:0);
 if(Lamp){Light->SetMobility(EComponentMobility::Movable);OriginalIntensity=Light->Intensity;}
 Probe=Lamp?FVector(-2320,1490,1206):FVector(-2110,1470,1206);
 Aim=Lamp?FVector(-2028,1842,1455):FVector(-1840,1520,1260);
}
void AIndustrialOperational::Finish(bool Pass,const FString& Detail){
 UE_LOG(LogTemp,Display,TEXT("AUDITOR_TASK_TEST %s id=%s detail=%s"),Pass?TEXT("PASS"):TEXT("FAIL"),*CaseId,*Detail);
 Done=true;PhaseAge=0;
 if(!CapturePrefix.IsEmpty()&&Pass)FScreenshotRequest::RequestScreenshot(CapturePrefix+TEXT("-after.png"),false,false);
 else if(FParse::Param(FCommandLine::Get(),TEXT("AuditorTestExit")))FPlatformMisc::RequestExitWithStatus(false,Pass?0:1);
}
void AIndustrialOperational::Tick(float Dt){
 Super::Tick(Dt);Age+=Dt;PhaseAge+=Dt;
 if(Done){if(PhaseAge>1&&IFileManager::Get().FileExists(*(CapturePrefix+TEXT("-after.png"))))FPlatformMisc::RequestExitWithStatus(false,0);else if(PhaseAge>30)FPlatformMisc::RequestExitWithStatus(false,2);return;}
 auto* P=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0));if(!Target||!P||!P->Controller)return;
 if(!Ready){InitialPosition=P->GetActorLocation();InitialRotation=P->Controller->GetControlRotation();Ready=true;}
 Moved|=FVector::Dist2D(InitialPosition,P->GetActorLocation())>25||!InitialRotation.Equals(P->Controller->GetControlRotation(),3.f);
 const FVector Eye=P->Camera->GetComponentLocation(),D=Aim-Eye;
 FHitResult Hit;FCollisionQueryParams Query(SCENE_QUERY_STAT(IndustrialWatch),false,P);
 GetWorld()->LineTraceSingleByChannel(Hit,Eye,Aim+D.GetSafeNormal()*150.f,ECC_Visibility,Query);
 const bool Visible=Moved&&D.Size()<650&&FVector::DotProduct(P->Controller->GetControlRotation().Vector(),D.GetSafeNormal())>.7f&&Hit.GetActor()==Target;
 if(!Changed){
  Watch=Visible?Watch+Dt:0.f;
  if(Watch>=6&&Bug){
   if(CaseId==TEXT("I20")){Panel->SetScalarParameterValue(TEXT("Emissive Intesity"),0);Light->SetIntensity(0);}
   else{
    Panel->SetScalarParameterValue(TEXT("EmissiveLevel"),0);
    auto* Mesh=Target->GetStaticMeshComponent();for(int i=1;i<Mesh->GetNumMaterials();++i)Mesh->SetMaterial(i,OffMaterial);
   }
   Changed=true;UE_LOG(LogTemp,Display,TEXT("AUDITOR_OPERATIONAL_STATE id=%s on=0 observed_seconds=%.2f"),*CaseId,Watch);
  }
 }
 if(!Testing)return;
 if(Age>30){Finish(false,FString::Printf(TEXT("Observation timed out phase=%d watch=%.2f hit=%s"),Phase,Watch,*GetNameSafe(Hit.GetActor())));return;}
 if(Age<(CapturePrefix.IsEmpty()?1.f:7.f))return;
 auto View=[&](FVector A){P->GetCharacterMovement()->StopMovementImmediately();P->SetActorLocation(Probe);P->Controller->SetControlRotation((A-P->Camera->GetComponentLocation()).Rotation());};
 if(Phase==0){View(Probe+FVector(0,-200,100));Phase=1;PhaseAge=0;}
 else if(Phase==1&&PhaseAge>1){
  if(Changed){Finish(false,TEXT("State changed before being observed"));return;}
  View(Aim);Phase=2;PhaseAge=0;
 }else if(Phase==2&&PhaseAge>3){
  if(Changed||Watch<2.f){Finish(false,FString::Printf(TEXT("Initial state/visibility failed watch=%.2f hit=%s position=%s"),Watch,*GetNameSafe(Hit.GetActor()),*P->GetActorLocation().ToString()));return;}
  BeforeRecorded=true;
  if(!CapturePrefix.IsEmpty())FScreenshotRequest::RequestScreenshot(CapturePrefix+TEXT("-before.png"),false,false);
  Phase=3;PhaseAge=0;
 }else if(Phase==3&&PhaseAge>5){
  bool Pass=BeforeRecorded&&Target->GetActorTransform().Equals(Original,.01)&&!Target->IsHidden()&&(Changed==Bug);
  if(CaseId==TEXT("I20")){
   float Emission=-1;Panel->GetScalarParameterValue(TEXT("Emissive Intesity"),Emission);
   Pass&=Bug?(Light->Intensity==0&&Emission==0):(Light->Intensity==OriginalIntensity&&OriginalIntensity>0);
  }else{
   auto* Mesh=Target->GetStaticMeshComponent();
   for(int i=1;i<Mesh->GetNumMaterials();++i)Pass&=Mesh->GetMaterial(i)==(Bug?OffMaterial.Get():OriginalMaterials[i].Get());
   float Emission=-1;Panel->GetScalarParameterValue(TEXT("EmissiveLevel"),Emission);Pass&=Bug?Emission==0:Emission>0;
  }
  Finish(Pass,Bug?TEXT("Observed on state then spontaneous shutdown; geometry retained"):TEXT("Paired control remains on throughout the same observation"));
 }
}

