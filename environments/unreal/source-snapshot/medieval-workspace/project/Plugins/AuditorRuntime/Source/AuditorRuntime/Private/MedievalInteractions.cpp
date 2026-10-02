#include "MedievalInteractions.h"
#include "AuditorPlaytest.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/SceneComponent.h"
#include "GameFramework/RotatingMovementComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "HAL/FileManager.h"
#include "UnrealClient.h"
AMedievalInteractions::AMedievalInteractions(){PrimaryActorTick.bCanEverTick=true;}
void AMedievalInteractions::Configure(const FString& Task){
 TaskId=Task;
 for(TActorIterator<AStaticMeshActor> I(GetWorld());I;++I){
  if(I->ActorHasTag(TEXT("auditor_actor:InteractiveBasket")))Basket=*I;
 }
 if(Basket){
  Basket->SetMobility(EComponentMobility::Movable);auto* Mesh=Basket->GetStaticMeshComponent();
  const auto T=Mesh->GetComponentTransform();const auto B=Mesh->Bounds;BasketCenter=B.Origin;
  Mesh->SetSimulatePhysics(false);Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
  Body=NewObject<UBoxComponent>(Basket);Basket->AddInstanceComponent(Body);Basket->SetRootComponent(Body);
  Body->SetBoxExtent(B.BoxExtent*FVector(.92,.92,.98));Body->SetCollisionProfileName(TEXT("PhysicsActor"));Body->SetCollisionResponseToAllChannels(ECR_Block);Body->SetUseCCD(true);Body->SetNotifyRigidBodyCollision(true);Body->RegisterComponent();Body->SetWorldLocation(BasketCenter);Body->SetSimulatePhysics(false);
  Mesh->AttachToComponent(Body,FAttachmentTransformRules::KeepWorldTransform);Mesh->SetWorldTransform(T);
  Body->SetLinearDamping(.5);Body->SetAngularDamping(2);Body->OnComponentHit.AddDynamic(this,&AMedievalInteractions::Contact);
 }
 for(TActorIterator<AActor> I(GetWorld());I;++I) if(I->ActorHasTag(TEXT("auditor_windmill"))){Windmill=*I;Rotor=I->FindComponentByClass<URotatingMovementComponent>();if(Rotor)OriginalRate=Rotor->RotationRate;break;}
 if(TaskId==TEXT("MV17")&&Windmill&&Rotor&&!FParse::Param(FCommandLine::Get(),TEXT("AuditorControl"))){
  // Rotate the existing shaft and blades together; mount the shaft into the roof peak.
  Windmill->SetActorRotation(Windmill->GetActorQuat()*FRotator(90,0,0).Quaternion());
  Windmill->SetActorLocation(FVector(40471.2,29492.86,-2388));
  UE_LOG(LogTemp,Display,TEXT("CONFIGURATION_WINDMILL horizontal rooftop mounting"));
 }
 CommonTest=FParse::Param(FCommandLine::Get(),TEXT("AuditorMedievalInteractionTest"));
 Testing=CommonTest||(FParse::Param(FCommandLine::Get(),TEXT("AuditorTaskTest"))&&HandlesTest());
}
bool AMedievalInteractions::HandlesTest() const{return TaskId==TEXT("MV06")||TaskId==TEXT("MV14")||TaskId==TEXT("MV17");}
FString AMedievalInteractions::Interact(){
 auto* P=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0));if(!P||!P->Controller)return TEXT("not_ready");
 FVector E=P->Camera->GetComponentLocation();FHitResult H;FCollisionQueryParams Q(SCENE_QUERY_STAT(MedievalInteract),false,P);
 GetWorld()->LineTraceSingleByChannel(H,E,E+P->Controller->GetControlRotation().Vector()*250,ECC_Visibility,Q);
 if(Basket&&H.GetActor()==Basket&&(!Released||Age-ReleaseAge>.75f)){
  const FVector PushFrom=Body->GetComponentLocation();
  // Apply a small horizontal impulse at the current position; no lift or teleport.
  FVector Direction=(PushFrom-P->GetActorLocation()).GetSafeNormal2D();
  if(Direction.IsNearlyZero())Direction=P->Controller->GetControlRotation().Vector().GetSafeNormal2D();
  if(Body->IsSimulatingPhysics()){Body->SetPhysicsLinearVelocity(FVector::ZeroVector);Body->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);}
  Body->SetCollisionResponseToChannel(ECC_Pawn,ECR_Ignore);
  Body->SetSimulatePhysics(true);Body->SetMassOverrideInKg(NAME_None,1,true);Body->WakeAllRigidBodies();
  Body->AddImpulse(Direction*140.f,NAME_None,true);
  Released=true;ReleaseAge=Age;SettleAge=0;LastPushPosition=PushFrom;
  UE_LOG(LogTemp,Display,TEXT("AUDITOR_BASKET_PUSH task=%s position=%s direction=%s"),*TaskId,*PushFrom.ToString(),*Direction.ToString());
  return TEXT("interacted");
 }
 return TEXT("not_interactable");
}
void AMedievalInteractions::Contact(UPrimitiveComponent*,AActor* Other,UPrimitiveComponent*,FVector,const FHitResult& H){
 if(!Released||!Other||Other->IsA<APawn>()||H.ImpactNormal.Z<.6)return;
 ++Contacts;
 if(TaskId==TEXT("MV06")&&Age-LastBounce>.3){Body->SetPhysicsLinearVelocity(FVector(0,0,310));LastBounce=Age;++Bounces;}
}
void AMedievalInteractions::Tick(float Dt){
 Super::Tick(Dt);Age+=Dt;
 if(CapturePending){if(IFileManager::Get().FileExists(*CapturePath))FPlatformMisc::RequestExitWithStatus(false,ExitCode);else if(Age-CaptureAge>30)FPlatformMisc::RequestExitWithStatus(false,2);return;}
 auto* P=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0));
 if(Body&&Released){
  if(Body->IsSimulatingPhysics()&&TaskId!=TEXT("MV06")){
   const bool Resting=Age-ReleaseAge>.8f&&Body->GetPhysicsLinearVelocity().Size()<5&&Body->GetPhysicsAngularVelocityInDegrees().Size()<5;
   SettleAge=Resting?SettleAge+Dt:0;
   if(SettleAge>.5f){Body->SetSimulatePhysics(false);UE_LOG(LogTemp,Display,TEXT("AUDITOR_BASKET_SETTLED task=%s position=%s"),*TaskId,*Body->GetComponentLocation().ToString());}
  }
  // Restore solid collision once the player is clear; never trap an overlapping capsule.
  if(!Body->IsSimulatingPhysics()&&P&&FVector::Dist2D(P->GetActorLocation(),Body->GetComponentLocation())>Body->Bounds.BoxExtent.Size2D()+P->GetCapsuleComponent()->GetScaledCapsuleRadius()+5)
   Body->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);
 }
 if(Windmill&&Rotor&&TaskId==TEXT("MV14")&&P&&P->Controller){
  FVector Center,Extent;Windmill->GetActorBounds(false,Center,Extent);
  const FVector Delta=Center-P->Camera->GetComponentLocation();
  const float Facing=FVector::DotProduct(P->Controller->GetControlRotation().Vector(),Delta.GetSafeNormal());
  FHitResult Hit;FCollisionQueryParams Params(SCENE_QUERY_STAT(MedievalWindmillView),true,P);
  GetWorld()->LineTraceSingleByChannel(Hit,P->Camera->GetComponentLocation(),Center,ECC_Visibility,Params);
  if(Facing>.85f&&Delta.Size()<2400&&(!Hit.bBlockingHit||Hit.GetActor()==Windmill))WindmillSeen=true;
  if(WindmillSeen&&FVector::DotProduct(P->Controller->GetControlRotation().Vector().GetSafeNormal2D(),Delta.GetSafeNormal2D())<0&&!WindmillChanged){Rotor->RotationRate=OriginalRate*-1.f;WindmillChanged=true;}
 }
 if(Testing)TestStep(Dt);
}
void AMedievalInteractions::Finish(bool Pass,const FString& Detail){
 UE_LOG(LogTemp,Display,TEXT("AUDITOR_TASK_TEST %s id=%s detail=%s"),Pass?TEXT("PASS"):TEXT("FAIL"),*TaskId,*Detail);Testing=false;
 if(FParse::Value(FCommandLine::Get(),TEXT("AuditorCaptureOnTest="),CapturePath)){FScreenshotRequest::RequestScreenshot(CapturePath,false,false);CapturePending=true;CaptureAge=Age;ExitCode=Pass?0:1;return;}
 if(FParse::Param(FCommandLine::Get(),TEXT("AuditorTestExit")))FPlatformMisc::RequestExitWithStatus(false,Pass?0:1);
}
void AMedievalInteractions::TestStep(float Dt){
 auto* P=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0));FString CaptureWarmup;if(!P||!P->Controller||Age<(FParse::Value(FCommandLine::Get(),TEXT("AuditorCaptureOnTest="),CaptureWarmup)?6.f:1.f))return;
 PhaseAge+=Dt;if(Age>(CommonTest?35.f:18.f)){Finish(false,FString::Printf(TEXT("Interaction verification timed out phase=%d position=%s"),Phase,*P->GetActorLocation().ToString()));return;}
 auto View=[&](FVector Pos,FVector Aim){P->GetCharacterMovement()->StopMovementImmediately();P->SetActorLocation(Pos);P->Controller->SetControlRotation((Aim-P->Camera->GetComponentLocation()).Rotation());};
 if(TaskId==TEXT("MV17")){
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
 if(Windmill&&(TaskId==TEXT("MV14")||(CommonTest&&!Basket))){
  if(!Rotor||!Rotor->UpdatedComponent){Finish(false,TEXT("Authored windmill rotating component missing"));return;}
  FVector Center,Extent;Windmill->GetActorBounds(false,Center,Extent);
  auto Rotation=[&](){return Rotor->UpdatedComponent->GetComponentQuat();};
  auto Delta=[&](){FQuat Q=Rotation()*WindmillSample.Inverse();Q.Normalize();if(Q.W<0)Q=Q*-1.f;return FVector(Q.X,Q.Y,Q.Z);};
  if(Phase==0){View(P->Region->SpawnLocation,Center);WindmillSample=Rotation();Phase=1;PhaseAge=0;}
  else if(Phase==1&&PhaseAge>.8f){
   WindmillBefore=Delta();
   if((TaskId==TEXT("MV14")&&!WindmillSeen)||WindmillChanged||WindmillBefore.Size()<.04f){Finish(false,TEXT("Windmill must visibly rotate normally before looking away"));return;}
   P->Controller->SetControlRotation(P->Controller->GetControlRotation()+FRotator(0,180,0));Phase=2;PhaseAge=0;
  }else if(Phase==2&&PhaseAge>.4f){View(P->Region->SpawnLocation,Center);WindmillSample=Rotation();Phase=3;PhaseAge=0;}
  else if(Phase==3&&PhaseAge>.8f){const FVector After=Delta();UE_LOG(LogTemp,Display,TEXT("MEDIEVAL_WINDMILL_DEBUG changed=%d before=%s after=%s original=%s current=%s"),WindmillChanged,*WindmillBefore.ToString(),*After.ToString(),*OriginalRate.ToString(),*Rotor->RotationRate.ToString());const float Dot=FVector::DotProduct(WindmillBefore,After);Finish(After.Size()>.04f&&(TaskId==TEXT("MV14")?(WindmillChanged&&Dot<0):(!WindmillChanged&&Dot>0)),TaskId==TEXT("MV14")?TEXT("Actual authored blade rotation reverses after looking away and stays reversed on return"):TEXT("Baseline authored blades retain their rotation direction after looking away and back"));}
 }else if(CommonTest&&Basket&&TaskId!=TEXT("MV06")){
  auto WalkIntoBasket=[&](){const FVector D=Body->GetComponentLocation()-P->GetActorLocation();P->AddMovementInput(FVector(D.X,D.Y,0).GetSafeNormal());};
  auto AimAndPush=[&](){P->GetCharacterMovement()->StopMovementImmediately();P->Controller->SetControlRotation((Body->GetComponentLocation()-P->Camera->GetComponentLocation()).Rotation());const FVector Before=Body->GetComponentLocation();return Interact()==TEXT("interacted")&&FVector::Dist(Before,Body->GetComponentLocation())<.1f;};
  if(Phase==0){FVector Pos=BasketCenter+FVector(140,0,0);Pos.Z=P->Region->SpawnLocation.Z;View(Pos,BasketCenter);Phase=1;PhaseAge=0;}
  else if(Phase==1){
   WalkIntoBasket();
   if(PhaseAge>1.2f){
    if(FVector::Dist(Body->GetComponentLocation(),BasketCenter)>1||Body->IsSimulatingPhysics()){Finish(false,TEXT("Approaching kicked the idle basket"));return;}
    if(!AimAndPush()){Finish(false,TEXT("Basket not reachable by E after approaching"));return;}
    View(P->GetActorLocation()+FVector(140,0,0),BasketCenter);Phase=2;PhaseAge=0;
   }
  }else if((Phase==2||Phase==4)&&PhaseAge>6){
   if(Contacts==0||Bounces!=0||FVector::Dist2D(Body->GetComponentLocation(),LastPushPosition)<3||FMath::Abs(Body->GetComponentLocation().Z-LastPushPosition.Z)>5||Body->IsSimulatingPhysics()||Body->GetCollisionResponseToChannel(ECC_Pawn)!=ECR_Block){Finish(false,TEXT("Pushed baseline basket must move horizontally and settle on the ground"));return;}
   if(Phase==4){Finish(true,TEXT("Walking cannot kick idle basket; two E pushes move it without teleporting and both settle"));return;}
   BasketRestPoint=Body->GetComponentLocation();Phase=3;PhaseAge=0;
  }else if(Phase==3){
   WalkIntoBasket();
   if(PhaseAge>1.5f){
    if(FVector::Dist(Body->GetComponentLocation(),BasketRestPoint)>1){Finish(false,TEXT("Approaching kicked the settled basket"));return;}
    if(!AimAndPush()){Finish(false,TEXT("Second E interaction failed"));return;}
    View(P->GetActorLocation()+FVector(140,0,0),BasketRestPoint);Phase=4;PhaseAge=0;
   }
  }
 }else if(TaskId==TEXT("MV06")){
  if(Phase==0){FVector Pos=BasketCenter+FVector(140,0,0);Pos.Z=P->Region->SpawnLocation.Z;View(Pos,BasketCenter);Phase=1;PhaseAge=0;}
  else if(Phase==1&&PhaseAge>.3){const bool Hit=Interact()==TEXT("interacted");if(!Hit){Finish(false,TEXT("Basket not reachable by E trace"));return;}View(P->GetActorLocation()+FVector(100,0,0),BasketCenter);Phase=2;PhaseAge=0;}
  else if(Phase==2&&PhaseAge>5){Finish(Contacts>0&&(TaskId==TEXT("MV06")?Bounces>=3:(Bounces==0&&Body->GetPhysicsLinearVelocity().Size()<5)),TEXT("E pushes basket horizontally; real ground contacts cause repeated rebounds in the bug"));}
 }else Finish(true,TEXT("No E interaction in this scene"));
}
