#include "ResidentialScenario.h"
#include "AuditorTasks.h"
#include "AuditorPlaytest.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/OverlapResult.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "HAL/FileManager.h"
#include "UnrealClient.h"

namespace {
FVector V(const TSharedPtr<FJsonObject>& S,const TCHAR* Key,FVector Default=FVector::ZeroVector) {
    const TArray<TSharedPtr<FJsonValue>>* A; if(!S || !S->TryGetArrayField(Key,A) || A->Num()!=3) return Default;
    return FVector((*A)[0]->AsNumber(),(*A)[1]->AsNumber(),(*A)[2]->AsNumber());
}
float N(const TSharedPtr<FJsonObject>& S,const TCHAR* Key,float Default=0) { double D; return S && S->TryGetNumberField(Key,D)?D:Default; }
AAuditorCharacter* Player(UWorld* W) { return Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(W,0)); }
}
#define VectorField V
#include "ConfigurationPose.inl"
#undef VectorField

AResidentialScenario::AResidentialScenario() { PrimaryActorTick.bCanEverTick=true; RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("Root")); }
AStaticMeshActor* AResidentialScenario::Find(const FString& Name) const {
    for(TActorIterator<AStaticMeshActor> I(GetWorld());I;++I) if(I->ActorHasTag(FName(*(TEXT("auditor_actor:")+Name))))return *I;
    return nullptr;
}
AStaticMeshActor* AResidentialScenario::Copy(AStaticMeshActor* Source) {
    if(!Source)return nullptr;
    auto* A=GetWorld()->SpawnActor<AStaticMeshActor>(); A->SetMobility(EComponentMobility::Movable);
    auto* C=A->GetStaticMeshComponent();auto* S=Source->GetStaticMeshComponent();C->SetStaticMesh(S->GetStaticMesh());
    for(int I=0;I<S->GetNumMaterials();++I)C->SetMaterial(I,S->GetMaterial(I));
    C->SetCollisionProfileName(S->GetCollisionProfileName());A->SetActorTransform(Source->GetActorTransform());return A;
}
void AResidentialScenario::SetupCommon() {
    Fan=Find(TEXT("StaticMeshActor_500")); if(Fan){FanOriginal=Fan->GetActorTransform();Fan->SetMobility(EComponentMobility::Movable);}
    // Move the existing three-piece cabinet from the inaccessible alcove to
    // the bedroom wall. Identical usable cabinet geometry in every clean/task map.
    const FVector OldBase(-1605.020933,-970.837238,440.31543),NewBase(-1590,-530,440.31543);
    const FQuat Rotation=FRotator(0,-90,0).Quaternion();
    for(const TCHAR* Name:{TEXT("StaticMeshActor_2070"),TEXT("StaticMeshActor_2071"),TEXT("StaticMeshActor_2072")})
        if(auto* Piece=Find(Name)){Piece->SetMobility(EComponentMobility::Movable);Piece->SetActorLocation(NewBase+Rotation.RotateVector(Piece->GetActorLocation()-OldBase));Piece->SetActorRotation(Rotation*Piece->GetActorQuat());}
    Door=Find(TEXT("StaticMeshActor_2071"));if(Door){DoorOriginal=Door->GetActorTransform();Door->SetMobility(EComponentMobility::Movable);}
    Stool=Find(TEXT("StaticMeshActor_67"));
    // Existing mug and table gain the same lift/release interaction in all maps.
    auto* Source=Find(TEXT("StaticMeshActor_1010"));
    if(Source){
        Cup=Copy(Source);CupOriginal=Source->GetActorTransform();CupCenter=Source->GetStaticMeshComponent()->Bounds.Origin;
        CupMaterial=Source->GetStaticMeshComponent()->GetMaterial(0);
        Source->SetActorHiddenInGame(true);Source->SetActorEnableCollision(false);
        auto* Mesh=Cup->GetStaticMeshComponent();Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        CupBody=NewObject<UBoxComponent>(Cup);Cup->AddInstanceComponent(CupBody);Cup->SetRootComponent(CupBody);
        CupBody->SetBoxExtent(FVector(4,4,4.2));CupBody->SetCollisionProfileName(TEXT("PhysicsActor"));
        CupBody->SetCollisionResponseToAllChannels(ECR_Block);CupBody->SetNotifyRigidBodyCollision(true);CupBody->SetUseCCD(true);CupBody->RegisterComponent();CupBody->SetWorldLocation(CupCenter);
        Mesh->AttachToComponent(CupBody,FAttachmentTransformRules::KeepWorldTransform);Mesh->SetWorldTransform(CupOriginal);Mesh->UpdateBounds();
        CupBody->SetLinearDamping(.3);CupBody->SetAngularDamping(2);CupBody->OnComponentHit.AddDynamic(this,&AResidentialScenario::CupContact);
    }
}
bool AResidentialScenario::Configure(AAuditorTasks* Owner,TSharedPtr<FJsonObject> Definition) {
    Catalog=Owner;Spec=Definition;Id=Owner->ActiveId;
    Inject=Spec.IsValid() && !FParse::Param(FCommandLine::Get(),TEXT("AuditorControl"));
    Test=FParse::Param(FCommandLine::Get(),TEXT("AuditorTaskTest"));Review=FParse::Param(FCommandLine::Get(),TEXT("AuditorReview"));
    if(Spec)Kind=Spec->GetStringField(TEXT("scenario"));
    SetupCommon();
    if(Spec){
        const auto Name=Spec->GetStringField(TEXT("target"));Target=Name.IsEmpty()?nullptr:Find(Name);
        if(Name==TEXT("StaticMeshActor_1010"))Target=Cup;
        if(!Name.IsEmpty()&&!Target){Finish(false,TEXT("Missing authored target"));return false;}
        Probe=V(Spec,TEXT("probe"));FarProbe=V(Spec,TEXT("far_probe"),Probe);
        if(Target){Original=Target->GetActorTransform();Center=Target->GetStaticMeshComponent()->Bounds.Origin;Target->SetMobility(EComponentMobility::Movable);}
        else Center=V(Spec,TEXT("aim"));
    }
    if(Kind==TEXT("door_penetration")&&!SetupRoomDoor()){Finish(false,TEXT("Missing door/box setup"));return false;}
    if(Inject){
        if(Kind==TEXT("existing_missing_shadow")){Target->GetStaticMeshComponent()->SetCastShadow(false);Target->GetStaticMeshComponent()->bAffectDistanceFieldLighting=false;Target->GetStaticMeshComponent()->MarkRenderStateDirty();}
        else if(Kind==TEXT("configuration_pose"))ApplyConfigurationPose(Target,Spec);
        else if(Kind==TEXT("floating")||Kind==TEXT("intersection"))Target->AddActorWorldOffset(V(Spec,TEXT("offset")));
        else if(Kind==TEXT("proportion"))Target->SetActorScale3D(Original.GetScale3D()*V(Spec,TEXT("scale")));
        else if(Kind==TEXT("penetration"))Target->SetActorEnableCollision(false);
        else if(Kind==TEXT("obstruction")){
            Barrier=NewObject<UBoxComponent>(this);AddInstanceComponent(Barrier);Barrier->SetupAttachment(RootComponent);Barrier->SetBoxExtent(V(Spec,TEXT("extent")));
            Barrier->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);Barrier->SetCollisionResponseToAllChannels(ECR_Ignore);Barrier->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);Barrier->RegisterComponent();Barrier->SetWorldLocation(V(Spec,TEXT("position")));
        }
        else if(Kind==TEXT("shadow")){
            Extra=Copy(Target);Extra->SetActorEnableCollision(false);Extra->GetStaticMeshComponent()->SetCastHiddenShadow(true);Extra->SetActorHiddenInGame(true);Extra->AddActorWorldOffset(V(Spec,TEXT("offset")));Target->GetStaticMeshComponent()->SetCastShadow(false);
        }
        else if(Kind==TEXT("layout")&&Stool){
            Stool->SetMobility(EComponentMobility::Movable);const auto B=Stool->GetStaticMeshComponent()->Bounds;
            Stool->AddActorWorldOffset(FVector(-1544,-553,441)-FVector(B.Origin.X,B.Origin.Y,B.Origin.Z-B.BoxExtent.Z));
        }
    }
    if(Kind==TEXT("view_appearance")){
        Extra=Copy(Target);Extra->SetActorEnableCollision(false);Target->SetActorHiddenInGame(true);
    }
    if(Kind==TEXT("proportion")&&Target)Center=Target->GetStaticMeshComponent()->Bounds.Origin;
    // Begin opted-in revisit tasks at their authored observation point.
    // Seen is still earned by the normal distance and visibility checks.
    bool StartObserved=false;
    if(Spec && Spec->TryGetBoolField(TEXT("start_at_observation"),StartObserved) && StartObserved)
        SetView(Probe,Center);
    Ready=true;return true;
}
void AResidentialScenario::SetView(FVector P,FVector Aim) {
    if(auto* Pawn=Player(GetWorld())){Pawn->GetCharacterMovement()->StopMovementImmediately();Pawn->SetActorLocation(P);Pawn->Controller->SetControlRotation((Aim-Pawn->Camera->GetComponentLocation()).Rotation());}
}
bool AResidentialScenario::InView(AStaticMeshActor* Object) const {
    auto* P=Player(GetWorld());if(!P||!P->Controller||!Object)return false;
    FVector E=P->Camera->GetComponentLocation(),D=Object->GetStaticMeshComponent()->Bounds.Origin-E;
    if(D.Size()>650||FVector::DotProduct(P->Controller->GetControlRotation().Vector(),D.GetSafeNormal())<.8)return false;
    FHitResult H;FCollisionQueryParams Q(SCENE_QUERY_STAT(ResidentialView),true,P);
    GetWorld()->LineTraceSingleByChannel(H,E,E+D,ECC_Visibility,Q);return !H.bBlockingHit||H.GetActor()==Object||H.GetActor()==Extra;
}
void AResidentialScenario::CupContact(UPrimitiveComponent*,AActor* Other,UPrimitiveComponent*,FVector,const FHitResult&) {
    if(!Released||Other!=Find(TEXT("StaticMeshActor_949")))return;
    ++Contacts;if(ContactAge<0)ContactAge=Age;
    if(Inject&&Kind==TEXT("contact")&&Age-LastSample>.35){
        // Wrong contact response is injected only after a real mug/table collision.
        CupBody->SetPhysicsLinearVelocity(FVector(0,0,260));LastSample=Age;++Excitations;
    }
}
bool AResidentialScenario::DoorBlocked(float Angle) const {
    if(!Door||!Stool)return false;
    FTransform T=DoorOriginal;T.SetRotation(DoorOriginal.GetRotation()*FRotator(0,-Angle,0).Quaternion());
    const FBox B=Door->GetStaticMeshComponent()->GetStaticMesh()->GetBoundingBox();
    TArray<FOverlapResult> Hits;FCollisionQueryParams Q(SCENE_QUERY_STAT(ResidentialDoor),false,Door);
    GetWorld()->OverlapMultiByChannel(Hits,T.TransformPosition(B.GetCenter()),T.GetRotation(),ECC_Pawn,FCollisionShape::MakeBox(B.GetExtent()*T.GetScale3D().GetAbs()),Q);
    return Hits.ContainsByPredicate([&](const FOverlapResult& H){return H.GetActor()==Stool;});
}
// The box and normal hinged motion are identical in the paired scenes.
// Only the response to a real door/box overlap is omitted in the treatment.
bool AResidentialScenario::SetupRoomDoor() {
    RoomDoor=Target;DoorBox=Copy(Find(TEXT("H15_BoxTemplate")));
    if(!RoomDoor||!DoorBox)return false;
    RoomDoorClosed=Original;RoomDoorClosed.SetRotation(FRotator(0,-90,0).Quaternion());
    RoomDoor->SetActorTransform(RoomDoorClosed);RoomDoor->SetActorEnableCollision(true);
    DoorBox->Tags.Add(TEXT("auditor_actor:H15_RuntimeBox"));
    DoorBox->SetActorHiddenInGame(false);DoorBox->SetActorEnableCollision(true);
    DoorBox->SetActorScale3D(V(Spec,TEXT("box_scale"),FVector::OneVector));
    DoorBox->SetActorLocation(V(Spec,TEXT("box_position")));
    const FBox B=DoorBox->GetStaticMeshComponent()->GetStaticMesh()->GetBoundingBox();
    DoorBox->AddActorWorldOffset(FVector(0,0,-B.Min.Z*DoorBox->GetActorScale3D().Z));
    BoxPlaced=DoorBox->GetActorTransform();
    DoorBox->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    DoorBoxBody=NewObject<UBoxComponent>(DoorBox);DoorBox->AddInstanceComponent(DoorBoxBody);
    DoorBoxBody->SetupAttachment(DoorBox->GetRootComponent());DoorBoxBody->SetBoxExtent(B.GetExtent());
    DoorBoxBody->SetRelativeLocation(B.GetCenter());DoorBoxBody->SetCollisionProfileName(TEXT("BlockAll"));DoorBoxBody->RegisterComponent();
    Center=RoomDoor->GetStaticMeshComponent()->Bounds.Origin;
    return !RoomDoorBlocked(0) && RoomDoorBlocked(45) && !RoomDoorBlocked(90);
}
bool AResidentialScenario::RoomDoorBlocked(float Angle) const {
    if(!RoomDoor||!DoorBoxBody)return false;
    FTransform T=RoomDoorClosed;T.SetRotation(RoomDoorClosed.GetRotation()*FRotator(0,-Angle,0).Quaternion());
    // Panel box excludes the protruding handle, so the scored overlap is solid wood.
    TArray<FOverlapResult> Hits;FCollisionQueryParams Q(SCENE_QUERY_STAT(ResidentialRoomDoor),false,RoomDoor);
    GetWorld()->OverlapMultiByChannel(Hits,T.TransformPosition(FVector(42,0,109)),T.GetRotation(),ECC_Pawn,
        FCollisionShape::MakeBox(FVector(42,2,105)*T.GetScale3D().GetAbs()),Q);
    return Hits.ContainsByPredicate([&](const FOverlapResult& H){return H.GetComponent()==DoorBoxBody;});
}
void AResidentialScenario::MoveRoomDoor(float Dt) {
    // Substep rotation queries to avoid tunnelling at low frame rates.
    float Remaining=FMath::Min(Dt,0.25f)*35;
    while(Remaining>KINDA_SMALL_NUMBER){
        const float Step=FMath::Min(Remaining,1.f),Next=FMath::Clamp(RoomDoorAngle+(RoomDoorRequested?Step:-Step),0.f,90.f);
        const bool Hit=RoomDoorBlocked(Next);
        if(Hit&&!Inject)break;
        DoorCrossedBox|=Hit;RoomDoorAngle=Next;Remaining-=Step;
    }
    RoomDoor->SetActorRotation(RoomDoorClosed.GetRotation()*FRotator(0,-RoomDoorAngle,0).Quaternion());
}
bool AResidentialScenario::CabinetAvailable() const {
    auto* P=Player(GetWorld());
    if(!Ready||!Door||!P||!P->Controller)return false;
    const FVector Eye=P->Camera->GetComponentLocation();
    const FVector LocalCenter=Door->GetStaticMeshComponent()->GetStaticMesh()->GetBoundingBox().GetCenter();
    // The closed position remains a usable focus while the panel swings open.
    const FVector Anchors[]={DoorOriginal.TransformPosition(LocalCenter),Door->GetStaticMeshComponent()->Bounds.Origin};
    auto* Body=Find(TEXT("StaticMeshActor_2070"));
    for(const FVector& Aim:Anchors){
        const FVector Delta=Aim-Eye;
        if(Delta.Size()>150 || FVector::DotProduct(P->Controller->GetControlRotation().Vector(),Delta.GetSafeNormal())<FMath::Cos(FMath::DegreesToRadians(18.f)))continue;
        FHitResult Hit;FCollisionQueryParams Query(SCENE_QUERY_STAT(CabinetVisibility),true,P);
        GetWorld()->LineTraceSingleByChannel(Hit,Eye,Aim,ECC_Visibility,Query);
        // A clear view of the cabinet is required, including when its panel is open.
        if(!Hit.bBlockingHit||Hit.GetActor()==Door||Hit.GetActor()==Body)return true;
    }
    return false;
}
AResidentialScenario::EInteraction AResidentialScenario::InteractionTarget() const {
    auto* P=Player(GetWorld());if(!Ready||!P||!P->Controller)return EInteraction::None;
    FHitResult H;FCollisionQueryParams Q(SCENE_QUERY_STAT(ResidentialInteract),false,P);
    const FVector E=P->Camera->GetComponentLocation();
    GetWorld()->LineTraceSingleByChannel(H,E,E+P->Controller->GetControlRotation().Vector()*250,ECC_Visibility,Q);
    if(RoomDoor&&H.GetActor()==RoomDoor)return EInteraction::RoomDoor;
    const bool CupAim=H.GetActor()==Cup || (H.GetActor()==Find(TEXT("StaticMeshActor_949"))&&FVector::Dist(H.ImpactPoint,CupCenter)<15);
    if(CupAim&&!Released)return EInteraction::Cup;
    return CabinetAvailable()?EInteraction::Cabinet:EInteraction::None;
}
FString AResidentialScenario::InteractionPrompt() const {
    if(InteractionTarget()!=EInteraction::Cabinet)return FString();
    return DoorRequested?TEXT("Close cabinet"):TEXT("Open cabinet");
}
FString AResidentialScenario::Interact() {
    switch(InteractionTarget()){
    case EInteraction::RoomDoor: RoomDoorRequested=!RoomDoorRequested;return TEXT("interacted");
    case EInteraction::Cup:
        CupBody->SetWorldLocation(CupCenter+FVector(0,0,35));CupBody->SetSimulatePhysics(true);CupBody->SetMassOverrideInKg(NAME_None,.35,true);CupBody->WakeAllRigidBodies();Released=true;ReleaseAge=Age;return TEXT("interacted");
    case EInteraction::Cabinet: DoorRequested=!DoorRequested;return TEXT("interacted");
    default:return TEXT("not_interactable");
    }
}
void AResidentialScenario::Tick(float Dt) {
    Super::Tick(Dt);if(!Ready)return;Age+=Dt;
    auto* P=Player(GetWorld());if(!P||!P->Controller)return;
    if(RoomDoor && !(Review&&Phase==90))MoveRoomDoor(Dt);
    if(Door){
        if(DoorRequested){const float Next=FMath::Min(80.f,DoorAngle+Dt*55);if(!DoorBlocked(Next))DoorAngle=Next;}
        else DoorAngle=FMath::Max(0.f,DoorAngle-Dt*55);
        Door->SetActorRotation((DoorOriginal.GetRotation()*FRotator(0,-DoorAngle,0).Quaternion()));
    }
    if(Target&&Spec){
        float D=FVector::Dist2D(P->GetActorLocation(),Center);float Facing=FVector::DotProduct(P->Controller->GetControlRotation().Vector(),(Center-P->Camera->GetComponentLocation()).GetSafeNormal());
        if(Kind==TEXT("visibility"))Target->SetActorHiddenInGame(Inject&&Facing>.97);
        if(Kind==TEXT("view_appearance"))Extra->SetActorScale3D(Original.GetScale3D()*((Inject&&D>N(Spec,TEXT("threshold")))?N(Spec,TEXT("factor")):1));
        if(Kind.StartsWith(TEXT("revisit_"))){
            bool Observed=InView(Target);
            if(!Left && Observed && (Kind==TEXT("revisit_fan")||D<N(Spec,TEXT("near"),210)))Seen=true;
            bool Departed=Kind==TEXT("revisit_fan")?P->GetActorLocation().Y<N(Spec,TEXT("bathroom_y")):(D>N(Spec,TEXT("far"),310)&&Facing<0);
            if(Seen&&Departed)Left=true;
            bool Returned=Observed&&(Kind==TEXT("revisit_fan")?P->GetActorLocation().Y>-950:D<N(Spec,TEXT("near"),210));
            if(Inject&&Seen&&Left&&Returned&&!Changed){
                Changed=true;
                if(Kind==TEXT("revisit_disappear")){Target->SetActorHiddenInGame(true);Target->SetActorEnableCollision(false);}
                if(Kind==TEXT("revisit_color")){
                    auto* WhiteCeramic=LoadObject<UMaterialInterface>(nullptr,TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
                    if(WhiteCeramic){auto* Glaze=UMaterialInstanceDynamic::Create(WhiteCeramic,Target);Glaze->SetVectorParameterValue(TEXT("Color"),FLinearColor(.65,.045,.012));Target->GetStaticMeshComponent()->SetMaterial(0,Glaze);}
                }
                UE_LOG(LogTemp,Display,TEXT("RESIDENTIAL_TRANSITION id=%s seen=%d left=%d"),*Id,Seen,Left);
            }
        }
    }
    if(Fan&&Kind==TEXT("revisit_fan")&&Changed){FanAngle+=Dt*95;Fan->SetActorRotation(FanOriginal.GetRotation()*FRotator(0,FanAngle,0).Quaternion());}
    if(Test||Review)StepVerification(Dt);
}
void AResidentialScenario::Finish(bool Pass,const FString& Detail) {
    UE_LOG(LogTemp,Display,TEXT("AUDITOR_TASK_TEST %s id=%s detail=%s control=%d"),Pass?TEXT("PASS"):TEXT("FAIL"),*Id,*Detail,!Inject);
    Test=false;
    if(Review){Verified&=Pass;if(Kind==TEXT("visibility"))SetView(Probe,Center);Phase=90;PhaseTime=0;return;}
    if(FParse::Param(FCommandLine::Get(),TEXT("AuditorTestExit")))FPlatformMisc::RequestExitWithStatus(false,Pass?0:1);
}
void AResidentialScenario::StepVerification(float Dt) {
    PhaseTime+=Dt;if(Age<.6)return;
    if(Age>45){Review=false;Finish(false,TEXT("Scenario verification timeout"));return;}
    auto* P=Player(GetWorld());P->DisableInput(Cast<APlayerController>(P->Controller));
    if(Phase==90){
        if(PhaseTime<(SnapshotIndex?0.2f:2.5f))return;
        FString Path;FParse::Value(FCommandLine::Get(),TEXT("AuditorCapture="),Path);
        if(SnapshotIndex)Path=FPaths::GetPath(Path)/FString::Printf(TEXT("%s-%02d.png"),*FPaths::GetBaseFilename(Path),SnapshotIndex);
        if(!Capturing){FScreenshotRequest::RequestScreenshot(Path,true,false);Capturing=true;}
        else if(IFileManager::Get().FileExists(*Path)){
            if((Kind==TEXT("contact")||Kind==TEXT("revisit_fan"))&&SnapshotIndex<5){++SnapshotIndex;Capturing=false;PhaseTime=0;}
            else if(FParse::Param(FCommandLine::Get(),TEXT("AuditorTestExit")))FPlatformMisc::RequestExitWithStatus(false,Verified?0:1);
        }
        return;
    }
    if(!Spec){if(Phase==0){SetView(P->Region->SpawnLocation,P->Region->SpawnLocation+P->Region->SpawnRotation.Vector()*500);Phase=1;PhaseTime=0;}else if(PhaseTime>2)Finish(true,TEXT("Clean shared scene"));return;}
    if(Phase==0){
        bool StartObserved=false;
        if(Spec->TryGetBoolField(TEXT("start_at_observation"),StartObserved) && StartObserved){
            const bool Initial=Seen&&!Left&&!Changed&&InView(Target)&&FVector::Dist2D(P->GetActorLocation(),Center)<N(Spec,TEXT("near"),210);
            UE_LOG(LogTemp,Display,TEXT("RESIDENTIAL_INITIAL_OBSERVATION %s id=%s"),Initial?TEXT("PASS"):TEXT("FAIL"),*Id);
            if(!Initial){Finish(false,TEXT("Task must begin near its visible target before any verification movement"));return;}
        }
        SetView(Probe,Center);Phase=1;PhaseTime=0;return;
    }
    if(Phase==1 && PhaseTime<.4)return;
    if(Kind.StartsWith(TEXT("revisit_"))){
        if(Phase==1){Verified=Seen&&!Changed;SetView(FarProbe,FarProbe+(FarProbe-Center).GetSafeNormal()*200);Phase=2;PhaseTime=0;}
        else if(Phase==2&&PhaseTime>.5){Verified&=Left&&!Changed;SetView(Probe,Center);Phase=3;PhaseTime=0;}
        else if(Phase==3&&PhaseTime>1){
            bool Outcome=Changed==Inject;
            if(Kind==TEXT("revisit_disappear"))Outcome&=Target->IsHidden()==Inject && Target->GetActorEnableCollision()!=Inject;
            if(Kind==TEXT("revisit_color"))Outcome&=(Target->GetStaticMeshComponent()->GetMaterial(0)!=CupMaterial)==Inject;
            if(Kind==TEXT("revisit_fan"))Outcome&=Inject?FanAngle>30:FMath::IsNearlyZero(FanAngle);
            Finish(Verified&&Outcome,TEXT("Observed initial state, departed, returned; persistent state matches treatment/control"));
        }return;
    }
    if(Kind==TEXT("contact")){
        if(Phase==1){Verified=Interact()==TEXT("interacted");Phase=2;PhaseTime=0;}
        else if(Phase==2&&PhaseTime>6){UE_LOG(LogTemp,Display,TEXT("RESIDENTIAL_CONTACTS count=%d impulses=%d velocity=%s"),Contacts,Excitations,*CupBody->GetPhysicsLinearVelocity().ToString());Finish(Verified&&Contacts>0&&(Inject?Excitations>=3:(Excitations==0&&CupBody->GetPhysicsLinearVelocity().Size()<8)),TEXT("Real mug/table contacts: treatment repeats energy injection; clean control settles"));}return;
    }
    if(Kind==TEXT("door_penetration")){
        if(Phase==1){Verified=!RoomDoorBlocked(0)&&RoomDoorBlocked(45)&&!RoomDoorBlocked(90)&&Interact()==TEXT("interacted");Phase=2;PhaseTime=0;}
        else if(Phase==2&&PhaseTime>3.2f){
            const bool Open=Inject?(RoomDoorAngle>89&&DoorCrossedBox):(RoomDoorAngle>5&&RoomDoorAngle<45&&!DoorCrossedBox);
            Verified&=Open&&DoorBox->GetActorTransform().Equals(BoxPlaced,.01f);
            UE_LOG(LogTemp,Display,TEXT("ROOM_DOOR_OPEN angle=%.2f crossed=%d box_fixed=%d"),RoomDoorAngle,DoorCrossedBox,DoorBox->GetActorTransform().Equals(BoxPlaced,.01f));
            SetView(Probe,RoomDoor->GetStaticMeshComponent()->Bounds.Origin);
            Verified&=Interact()==TEXT("interacted");Phase=3;PhaseTime=0;
        }
        else if(Phase==3&&PhaseTime>3.2f){
            Verified&=RoomDoorAngle<.01f&&DoorBox->GetActorTransform().Equals(BoxPlaced,.01f);
            SetView(Probe,Center);Verified&=Interact()==TEXT("interacted");Phase=4;PhaseTime=0;
        }
        else if(Phase==4&&PhaseTime>(Inject?1.28f:2.f)){
            const bool Overlap=RoomDoorBlocked(RoomDoorAngle);
            Verified&=Overlap==Inject&&DoorBox->GetActorTransform().Equals(BoxPlaced,.01f);
            SetView(Probe,FVector(-965,-470,515));
            // Keep this visible intersection for rendered QA only; normal play is continuous.
            Finish(Verified,FString::Printf(TEXT("Door/box geometry overlap=%d angle=%.2f; real interaction opens/closes/reopens; box fixed; control blocks"),Overlap,RoomDoorAngle));
        }return;
    }
    if(Kind==TEXT("existing_missing_shadow")){
        auto* Other=Find(TEXT("StaticMeshActor_919"));
        const bool Pass=Other&&Other->GetStaticMeshComponent()->CastShadow&&!Target->IsHidden()&&Target->GetActorEnableCollision()&&Target->GetActorTransform().Equals(Original,.01f)&&Target->GetStaticMeshComponent()->CastShadow!=Inject;
        SetView(Probe,Center-FVector(0,0,20));
        Finish(Pass,TEXT("Original cabinet vase and other existing vase stay in place, visible and solid; only target cast shadow changes; paired render required"));return;
    }
    if(Kind==TEXT("configuration_pose")){FString Detail;const bool Pass=CheckConfigurationPose(Target,Original,Spec,Detail);Finish(Pass,Detail);return;}
    if(Kind==TEXT("layout")){
        if(Phase==1){Verified=Interact()==TEXT("interacted");Phase=2;PhaseTime=0;}
        else if(Phase==2&&PhaseTime>2){UE_LOG(LogTemp,Display,TEXT("RESIDENTIAL_DOOR angle=%.2f"),DoorAngle);Finish(Verified&&(Inject?DoorAngle<50:DoorAngle>75),TEXT("Same door interaction: furniture blocks swing only in injected layout"));}return;
    }
    if(Kind==TEXT("visibility")){
        if(Phase==1){Verified=Target->IsHidden()==Inject;P->Controller->SetControlRotation(P->Controller->GetControlRotation()+FRotator(0,35,0));Phase=2;PhaseTime=0;}
        else if(Phase==2&&PhaseTime>.3)Finish(Verified&&!Target->IsHidden(),TEXT("View-dependent visibility is reversible; clean object stays visible"));return;
    }
    if(Kind==TEXT("view_appearance")){
        if(Phase==1){Verified=Extra->GetActorScale3D().Equals(Original.GetScale3D(),.01);SetView(FarProbe,Center);Phase=2;PhaseTime=0;}
        else if(Phase==2&&PhaseTime>.5)Finish(Verified&&Extra->GetActorScale3D().Equals(Original.GetScale3D()*(Inject?N(Spec,TEXT("factor")):1),.01),TEXT("Near/far rendering changes only in treatment; collision remains baseline"));return;
    }
    if(Kind==TEXT("penetration")){
        auto Sweep=[&](){TArray<FHitResult> H;FCollisionQueryParams Q(SCENE_QUERY_STAT(ResidentialPassage),false,P);for(TActorIterator<AActor>I(GetWorld());I;++I)if(*I!=Target)Q.AddIgnoredActor(*I);GetWorld()->SweepMultiByChannel(H,Center-FVector(100,0,0),Center+FVector(100,0,0),FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(30,90),Q);return H.ContainsByPredicate([&](const FHitResult& X){return X.GetActor()==Target;});};
        bool Actual=Sweep();Target->SetActorEnableCollision(true);bool Baseline=Sweep();Target->SetActorEnableCollision(!Inject);Finish(Baseline&&Actual!=Inject,TEXT("Real capsule sweep hits refrigerator in control and passes injected target"));return;
    }
    if(Kind==TEXT("obstruction")){
        TArray<FHitResult> H;FCollisionQueryParams Q(SCENE_QUERY_STAT(ResidentialBlocker),false,P);FVector C=V(Spec,TEXT("position"));GetWorld()->SweepMultiByChannel(H,C-FVector(0,65,0),C+FVector(0,65,0),FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(30,90),Q);
        bool Hit=H.ContainsByPredicate([](const FHitResult& X){return X.bBlockingHit;});Finish(Hit==Inject,TEXT("Internal passage is open in control and blocked in treatment"));return;
    }
    if(Kind==TEXT("floating")||Kind==TEXT("intersection"))Finish(Target->GetActorLocation().Equals(Original.GetLocation()+(Inject?V(Spec,TEXT("offset")):FVector::ZeroVector),.1),TEXT("Measured geometry displacement; paired rendered review required"));
    else if(Kind==TEXT("proportion")){
        auto* Stove=Find(TEXT("StaticMeshActor_183"));
        if(!Stove){Finish(false,TEXT("Missing stove scale reference"));return;}
        const auto A=Target->GetStaticMeshComponent()->Bounds,B=Stove->GetStaticMeshComponent()->Bounds;
        const auto Local=Target->GetStaticMeshComponent()->GetStaticMesh()->GetBounds();
        const FVector CleanBottom=Original.TransformPosition(Local.Origin-FVector(0,0,Local.BoxExtent.Z));
        const float BottomDelta=FMath::Abs(A.Origin.Z-A.BoxExtent.Z-CleanBottom.Z);
        const float WidthToStove=A.BoxExtent.X/B.BoxExtent.X;
        const float Overhang=A.Origin.X+A.BoxExtent.X-(B.Origin.X+B.BoxExtent.X);
        const bool Pass=BottomDelta<.1f&&FVector::Dist2D(Target->GetActorLocation(),Original.GetLocation())<.1f&&
            (Inject?(WidthToStove>.5f&&WidthToStove<.6f&&Overhang>4.f):(WidthToStove<.25f&&Overhang<0));
        Finish(Pass,FString::Printf(TEXT("Pot/stove width ratio %.3f; bottom delta %.3f cm; stove-edge overhang %.2f cm; treatment=%d"),WidthToStove,BottomDelta,Overhang,Inject));
    }
    else if(Kind==TEXT("shadow"))Finish(Inject?(Extra&&Extra->IsHidden()&&Extra->GetStaticMeshComponent()->bCastHiddenShadow&&!Target->GetStaticMeshComponent()->CastShadow):Target->GetStaticMeshComponent()->CastShadow,TEXT("Shadow-only mutation; paired rendered evidence required"));
    else Finish(false,TEXT("Unknown residential scenario"));
}
