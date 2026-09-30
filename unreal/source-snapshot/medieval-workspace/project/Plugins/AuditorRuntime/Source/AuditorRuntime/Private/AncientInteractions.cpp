#include "AncientInteractions.h"
#include "AuditorPlaytest.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
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
AAncientInteractions::AAncientInteractions(){PrimaryActorTick.bCanEverTick=true;}
void AAncientInteractions::Configure(const FString& Task){
 TaskId=Task;
 for(TActorIterator<AStaticMeshActor> I(GetWorld());I;++I){
  if(I->ActorHasTag(TEXT("auditor_actor:InteractiveBasket")))Basket=*I;
  if(I->ActorHasTag(TEXT("auditor_actor:InteractiveDoor")))Door=*I;
 }
 if(Basket){
  Basket->SetMobility(EComponentMobility::Movable);auto* Mesh=Basket->GetStaticMeshComponent();
  const auto T=Mesh->GetComponentTransform();const auto B=Mesh->Bounds;BasketCenter=B.Origin;
  Mesh->SetSimulatePhysics(false);Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
  Body=NewObject<UBoxComponent>(Basket);Basket->AddInstanceComponent(Body);Basket->SetRootComponent(Body);
  Body->SetBoxExtent(B.BoxExtent*FVector(.92,.92,.98));Body->SetCollisionProfileName(TEXT("PhysicsActor"));Body->SetCollisionResponseToAllChannels(ECR_Block);Body->SetUseCCD(true);Body->SetNotifyRigidBodyCollision(true);Body->RegisterComponent();Body->SetWorldLocation(BasketCenter);Body->SetSimulatePhysics(false);
  Mesh->AttachToComponent(Body,FAttachmentTransformRules::KeepWorldTransform);Mesh->SetWorldTransform(T);
  Body->SetLinearDamping(.5);Body->SetAngularDamping(2);Body->OnComponentHit.AddDynamic(this,&AAncientInteractions::Contact);
 }
 if(Door){
  Door->SetMobility(EComponentMobility::Movable);DoorOriginal=Door->GetActorTransform();
  // The source scene supplies a second copy of the same leaf, already swung open.
  // Keep both hinge positions, mirror the partner so both exterior faces agree.
  float Nearest=250.f;
  for(TActorIterator<AStaticMeshActor> I(GetWorld());I;++I){
   if(*I==Door||I->GetStaticMeshComponent()->GetStaticMesh()!=Door->GetStaticMeshComponent()->GetStaticMesh())continue;
   const float Distance=FVector::Dist(I->GetActorLocation(),Door->GetActorLocation());
   if(Distance<Nearest){Nearest=Distance;DoorOther=*I;}
  }
  if(DoorOther){
   DoorOther->SetMobility(EComponentMobility::Movable);
   FVector Scale=DoorOriginal.GetScale3D();Scale.X=-Scale.X;
   DoorOtherOriginal=FTransform(DoorOriginal.GetRotation(),DoorOther->GetActorLocation(),Scale);
   DoorOther->SetActorTransform(DoorOtherOriginal);
   DoorOther->SetActorRotation(DoorOtherOriginal.GetRotation()*FRotator(0,DoorOtherAngle,0).Quaternion());
   DoorOther->Tags.AddUnique(TEXT("auditor_actor:InteractiveDoorOther"));
  }
 }
 StairTest=FParse::Param(FCommandLine::Get(),TEXT("AuditorAncientStairTest"));
 CommonTest=StairTest||FParse::Param(FCommandLine::Get(),TEXT("AuditorAncientInteractionTest"));
 Testing=CommonTest||(FParse::Param(FCommandLine::Get(),TEXT("AuditorTaskTest"))&&HandlesTest());
}
bool AAncientInteractions::HandlesTest() const{return TaskId==TEXT("A09")||TaskId==TEXT("A17");}
FString AAncientInteractions::Interact(){
 auto* P=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0));if(!P||!P->Controller)return TEXT("not_ready");
 FVector E=P->Camera->GetComponentLocation();FHitResult H;FCollisionQueryParams Q(SCENE_QUERY_STAT(AncientInteract),false,P);
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
 if(Door&&H.GetActor()==Door){RequestedOpen=!RequestedOpen;UE_LOG(LogTemp,Display,TEXT("AUDITOR_DOUBLE_DOOR input=first open=%d other_open=%d"),RequestedOpen,OtherRequestedOpen);return TEXT("interacted");}
 if(DoorOther&&H.GetActor()==DoorOther){OtherRequestedOpen=!OtherRequestedOpen;UE_LOG(LogTemp,Display,TEXT("AUDITOR_DOUBLE_DOOR input=second open=%d other_open=%d"),OtherRequestedOpen,RequestedOpen);return TEXT("interacted");}
 return TEXT("not_interactable");
}
void AAncientInteractions::Contact(UPrimitiveComponent*,AActor* Other,UPrimitiveComponent*,FVector,const FHitResult& H){
 if(!Released||!Other||Other->IsA<APawn>()||H.ImpactNormal.Z<.6)return;
 ++Contacts;
 if(TaskId==TEXT("A09")&&Age-LastBounce>.3){Body->SetPhysicsLinearVelocity(FVector(0,0,310));LastBounce=Age;++Bounces;}
}
void AAncientInteractions::Tick(float Dt){
 Super::Tick(Dt);Age+=Dt;
 if(CapturePending){if(IFileManager::Get().FileExists(*CapturePath))FPlatformMisc::RequestExitWithStatus(false,ExitCode);else if(Age-CaptureAge>30)FPlatformMisc::RequestExitWithStatus(false,2);return;}
 auto* P=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0));
 if(Body&&Released){
  if(Body->IsSimulatingPhysics()&&TaskId!=TEXT("A09")){
   const bool Resting=Age-ReleaseAge>.8f&&Body->GetPhysicsLinearVelocity().Size()<5&&Body->GetPhysicsAngularVelocityInDegrees().Size()<5;
   SettleAge=Resting?SettleAge+Dt:0;
   if(SettleAge>.5f){Body->SetSimulatePhysics(false);UE_LOG(LogTemp,Display,TEXT("AUDITOR_BASKET_SETTLED task=%s position=%s"),*TaskId,*Body->GetComponentLocation().ToString());}
  }
  // Restore solid collision once the player is clear; never trap an overlapping capsule.
  if(!Body->IsSimulatingPhysics()&&P&&FVector::Dist2D(P->GetActorLocation(),Body->GetComponentLocation())>Body->Bounds.BoxExtent.Size2D()+P->GetCapsuleComponent()->GetScaledCapsuleRadius()+5)
   Body->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);
 }
 if(Door){
  if(TaskId==TEXT("A17")&&P&&P->Controller){
   const FVector D=Door->GetStaticMeshComponent()->Bounds.Origin-P->Camera->GetComponentLocation();const float Distance=D.Size2D();
   const float Facing=FVector::DotProduct(P->Controller->GetControlRotation().Vector(),D.GetSafeNormal());
   if(Distance<330&&Facing>.8)Seen=true;
   if(Seen&&Distance>550&&Facing<0)Left=true;
   if(Left&&Distance<330&&Facing>.8&&!Changed){RequestedOpen=true;Changed=true;}
  }
  DoorAngle=FMath::FInterpConstantTo(DoorAngle,RequestedOpen?85.f:0.f,Dt,65.f);
  Door->SetActorRotation((DoorOriginal.GetRotation()*FRotator(0,-DoorAngle,0).Quaternion()));
  DoorOtherAngle=FMath::FInterpConstantTo(DoorOtherAngle,OtherRequestedOpen?85.f:0.f,Dt,65.f);
  if(DoorOther)DoorOther->SetActorRotation(DoorOtherOriginal.GetRotation()*FRotator(0,DoorOtherAngle,0).Quaternion());
 }
 if(Testing)TestStep(Dt);
}
void AAncientInteractions::Finish(bool Pass,const FString& Detail){
 UE_LOG(LogTemp,Display,TEXT("AUDITOR_TASK_TEST %s id=%s detail=%s"),Pass?TEXT("PASS"):TEXT("FAIL"),*TaskId,*Detail);Testing=false;
 if(FParse::Value(FCommandLine::Get(),TEXT("AuditorCaptureOnTest="),CapturePath)){FScreenshotRequest::RequestScreenshot(CapturePath,false,false);CapturePending=true;CaptureAge=Age;ExitCode=Pass?0:1;return;}
 if(FParse::Param(FCommandLine::Get(),TEXT("AuditorTestExit")))FPlatformMisc::RequestExitWithStatus(false,Pass?0:1);
}
void AAncientInteractions::TestStep(float Dt){
 auto* P=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0));FString CaptureWarmup;if(!P||!P->Controller||Age<(FParse::Value(FCommandLine::Get(),TEXT("AuditorCaptureOnTest="),CaptureWarmup)?6.f:1.f))return;
 PhaseAge+=Dt;if(Age>((StairTest||CommonTest)?35.f:18.f)){Finish(false,FString::Printf(TEXT("Interaction verification timed out phase=%d position=%s"),Phase,*P->GetActorLocation().ToString()));return;}
 auto View=[&](FVector Pos,FVector Aim){P->GetCharacterMovement()->StopMovementImmediately();P->SetActorLocation(Pos);P->Controller->SetControlRotation((Aim-P->Camera->GetComponentLocation()).Rotation());};
 if(CommonTest&&Basket&&TaskId!=TEXT("A09")){
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
 }else if(TaskId==TEXT("A09")){
  if(Phase==0){FVector Pos=BasketCenter+FVector(140,0,0);Pos.Z=P->Region->SpawnLocation.Z;View(Pos,BasketCenter);Phase=1;PhaseAge=0;}
  else if(Phase==1&&PhaseAge>.3){const bool Hit=Interact()==TEXT("interacted");if(!Hit){Finish(false,TEXT("Basket not reachable by E trace"));return;}View(P->GetActorLocation()+FVector(100,0,0),BasketCenter);Phase=2;PhaseAge=0;}
  else if(Phase==2&&PhaseAge>5){Finish(Contacts>0&&(TaskId==TEXT("A09")?Bounces>=3:(Bounces==0&&Body->GetPhysicsLinearVelocity().Size()<5)),TEXT("E pushes basket horizontally; real ground contacts cause repeated rebounds in the bug"));}
 }else if(Door){
  const FVector C=Door->GetStaticMeshComponent()->Bounds.Origin;
  if(Phase==0){
   if(!DoorOther||!DoorOriginal.GetRotation().Equals(DoorOtherOriginal.GetRotation(),.001f)||DoorAngle>1||DoorOtherAngle<80||DoorOther->GetActorScale3D().X>=0){Finish(false,TEXT("One leaf must start closed and the other open, with matching exterior faces and opposite hinges"));return;}
   View(P->Region->SpawnLocation,C);Phase=1;PhaseAge=0;
  }
  else if(Phase==1&&PhaseAge>.4){
   if(CommonTest){if(Interact()!=TEXT("interacted")){Finish(false,TEXT("Door not reachable by E trace"));return;}Phase=4;PhaseAge=0;}
   else {FVector Far=P->Region->SpawnLocation+FVector(0,-450,0);View(Far,Far+FVector(0,-100,0));Phase=2;PhaseAge=0;}
  }else if(Phase==2&&PhaseAge>.4){View(P->Region->SpawnLocation,C);Phase=3;PhaseAge=0;}
  else if(Phase==3&&PhaseAge>2)Finish(Seen&&Left&&Changed&&DoorAngle>80&&DoorOther->GetStaticMeshComponent()->Bounds.Origin.Y>DoorOtherOriginal.GetLocation().Y+30&&C.Y>DoorOriginal.GetLocation().Y+30,TEXT("Door starts closed, opens only after leaving and returning without E"));
  else if(Phase==4&&PhaseAge>2){
   if(DoorAngle<80||C.Y<DoorOriginal.GetLocation().Y+30||DoorOther->GetStaticMeshComponent()->Bounds.Origin.Y<DoorOtherOriginal.GetLocation().Y+30){Finish(false,TEXT("Both door leaves must open inward"));return;}
   if(!StairTest){
    View(P->Region->SpawnLocation,DoorOther->GetStaticMeshComponent()->Bounds.Origin);
    if(Interact()!=TEXT("interacted")||OtherRequestedOpen||!RequestedOpen){Finish(false,TEXT("E on the second open leaf must close only that leaf"));return;}
    Phase=7;PhaseAge=0;return;
   }
   Phase=5;PhaseAge=0;
  }else if(!StairTest&&Phase==7&&PhaseAge>2){
   if(DoorAngle<80||DoorOtherAngle>1||!DoorOther->GetActorTransform().Equals(DoorOtherOriginal,.1f)){Finish(false,TEXT("Closing the second leaf must leave the first open"));return;}
   View(P->Region->SpawnLocation,DoorOther->GetStaticMeshComponent()->Bounds.Origin);
   if(Interact()!=TEXT("interacted")||!OtherRequestedOpen||!RequestedOpen){Finish(false,TEXT("E on the second closed leaf must reopen only that leaf"));return;}
   Phase=8;PhaseAge=0;
  }else if(!StairTest&&Phase==8&&PhaseAge>2){
   if(DoorAngle<80||DoorOtherAngle<80){Finish(false,TEXT("Independent reopen failed"));return;}
   View(P->Region->SpawnLocation,Door->GetStaticMeshComponent()->Bounds.Origin);
   if(Interact()!=TEXT("interacted")||RequestedOpen||!OtherRequestedOpen){Finish(false,TEXT("E on the first open leaf must close only that leaf"));return;}
   Phase=9;PhaseAge=0;
  }else if(!StairTest&&Phase==9&&PhaseAge>2){
   Finish(DoorAngle<1&&DoorOtherAngle>80&&Door->GetActorTransform().Equals(DoorOriginal,.1f),TEXT("One leaf starts open and one closed; both respond to E independently; both swing inward and restore initial state"));
  }else if(StairTest&&Phase>=5){
   // Walk with the same CharacterMovement/capsule as a reviewer; no teleport or jump.
   const FVector Target(520,Phase==5?7400:7045,0);
   const FVector Here=P->GetActorLocation();
   if(Phase==5&&Here.Z>145&&P->GetCharacterMovement()->IsMovingOnGround())ReachedLanding=true;
   if(FVector::Dist2D(Here,Target)<12&&P->GetCharacterMovement()->IsMovingOnGround()){
    P->GetCharacterMovement()->StopMovementImmediately();
    UE_LOG(LogTemp,Display,TEXT("AUDITOR_STAIR_WAYPOINT phase=%d position=%s"),Phase,*Here.ToString());
    if(Phase==5){Phase=6;PhaseAge=0;}
    else Finish(ReachedLanding,TEXT("E opens door; walked upstairs through doorway, down inside steps, and back outside without jumping"));
   }else P->AddMovementInput((Target-FVector(Here.X,Here.Y,0)).GetSafeNormal());
  }
 }else Finish(true,TEXT("No E interaction in this scene"));
}
