#include "ResidentialScenario.h"
#include "AuditorTasks.h"
#include "AuditorPlaytest.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Engine/TextRenderActor.h"
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
AStaticMeshActor* AResidentialScenario::Shape(const TCHAR* Asset,FVector P,FVector Scale,UMaterialInterface* Material) {
    auto* M=LoadObject<UStaticMesh>(nullptr,Asset); if(!M){UE_LOG(LogTemp,Error,TEXT("RESIDENTIAL_MISSING_SHAPE %s"),Asset);return nullptr;}
    auto* A=GetWorld()->SpawnActor<AStaticMeshActor>(); A->SetMobility(EComponentMobility::Movable);
    A->GetStaticMeshComponent()->SetStaticMesh(M);if(Material)A->GetStaticMeshComponent()->SetMaterial(0,Material);
    A->SetActorLocation(P);A->SetActorScale3D(Scale);A->SetActorEnableCollision(false);return A;
}
void AResidentialScenario::Pipe(FVector A,FVector B) {
    auto* Source=Find(TEXT("StaticMeshActor_500"));
    auto* P=Shape(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"),(A+B)*.5,FVector(.035,.035,FVector::Dist(A,B)/100),Source?Source->GetStaticMeshComponent()->GetMaterial(0):nullptr);
    if(P)P->SetActorRotation(FRotationMatrix::MakeFromZ(B-A).Rotator());
}
void AResidentialScenario::Label(FVector P,const FString& Text) {
    auto* A=GetWorld()->SpawnActor<ATextRenderActor>();A->SetActorLocation(P);A->SetActorRotation(FRotator::ZeroRotator);
    auto* C=A->GetTextRender();C->SetText(FText::FromString(Text));C->SetWorldSize(8);C->SetHorizontalAlignment(EHTA_Center);C->SetTextRenderColor(FColor(20,25,30));
}
void AResidentialScenario::SetupCommon() {
    Fan=Find(TEXT("StaticMeshActor_500")); if(Fan){FanOriginal=Fan->GetActorTransform();Fan->SetMobility(EComponentMobility::Movable);}
    Door=Find(TEXT("StaticMeshActor_2071"));if(Door){DoorOriginal=Door->GetActorTransform();Door->SetMobility(EComponentMobility::Movable);}
    Stool=Find(TEXT("StaticMeshActor_67"));
    // A usable labelled plumbing panel is shared by every task and clean control.
    auto* FinishSource=Find(TEXT("StaticMeshActor_500"));
    Shape(TEXT("/Engine/BasicShapes/Cube.Cube"),FVector(-312,-700,257),FVector(.04,1.65,1.3),FinishSource?FinishSource->GetStaticMeshComponent()->GetMaterial(0):nullptr);
    Label(FVector(-307,-660,307),TEXT("SINK OUT"));Label(FVector(-307,-745,307),TEXT("COLD IN"));
    Label(FVector(-307,-660,203),TEXT("DRAIN"));Label(FVector(-307,-745,203),TEXT("SUPPLY"));
    const bool Cross=Inject && Kind==TEXT("plumbing");
    for(int I=0;I<2;++I){
        float Y=I?-745:-660,EndY=Cross?(I?-660:-745):Y,X=I?-278:-292;
        FVector A(-306,Y,290),B(X,Y,280),C(X,EndY,230),D(-306,EndY,218);
        Pipe(A,B);Pipe(B,C);Pipe(C,D);
    }
    // Existing mug and table gain the same lift/release interaction in all maps.
    auto* Source=Find(TEXT("StaticMeshActor_1010"));
    if(Source){
        Cup=Copy(Source);CupOriginal=Source->GetActorTransform();CupCenter=Source->GetStaticMeshComponent()->Bounds.Origin;
        CupMaterial=Source->GetStaticMeshComponent()->GetMaterial(0);
        Source->SetActorHiddenInGame(true);Source->SetActorEnableCollision(false);
        auto* Mesh=Cup->GetStaticMeshComponent();Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        CupBody=NewObject<UBoxComponent>(Cup);Cup->AddInstanceComponent(CupBody);Cup->SetRootComponent(CupBody);
        CupBody->SetBoxExtent(FVector(4,4,4.2));CupBody->SetCollisionProfileName(TEXT("PhysicsActor"));
        CupBody->SetNotifyRigidBodyCollision(true);CupBody->SetUseCCD(true);CupBody->RegisterComponent();CupBody->SetWorldLocation(CupCenter);
        Mesh->AttachToComponent(CupBody,FAttachmentTransformRules::KeepWorldTransform);Mesh->SetWorldTransform(CupOriginal);
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
    if(Inject){
        if(Kind==TEXT("floating")||Kind==TEXT("intersection"))Target->AddActorWorldOffset(V(Spec,TEXT("offset")));
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
            Stool->AddActorWorldOffset(FVector(-1588,-914,441)-FVector(B.Origin.X,B.Origin.Y,B.Origin.Z-B.BoxExtent.Z));
        }
    }
    if(Kind==TEXT("view_appearance")){
        Extra=Copy(Target);Extra->SetActorEnableCollision(false);Target->SetActorHiddenInGame(true);
    }
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
FString AResidentialScenario::Interact() {
    auto* P=Player(GetWorld());if(!P||!P->Controller)return TEXT("not_ready");
    FHitResult H;FCollisionQueryParams Q(SCENE_QUERY_STAT(ResidentialInteract),true,P);FVector E=P->Camera->GetComponentLocation();
    GetWorld()->LineTraceSingleByChannel(H,E,E+P->Controller->GetControlRotation().Vector()*250,ECC_Visibility,Q);
    if(H.GetActor()==Cup && !Released){
        CupBody->SetWorldLocation(CupCenter+FVector(0,0,35));CupBody->SetSimulatePhysics(true);CupBody->SetMassOverrideInKg(NAME_None,.35,true);CupBody->WakeAllRigidBodies();Released=true;ReleaseAge=Age;return TEXT("interacted");
    }
    if(H.GetActor()==Door){DoorRequested=!DoorRequested;return TEXT("interacted");}
    return TEXT("not_interactable");
}
void AResidentialScenario::Tick(float Dt) {
    Super::Tick(Dt);if(!Ready)return;Age+=Dt;
    auto* P=Player(GetWorld());if(!P||!P->Controller)return;
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
                    auto* MID=UMaterialInstanceDynamic::Create(CupMaterial,Target);
                    TArray<FMaterialParameterInfo> Params;TArray<FGuid> Guids;CupMaterial->GetAllTextureParameterInfo(Params,Guids);
                    auto* Texture=UTexture2D::CreateTransient(1,1,PF_B8G8R8A8);Texture->SRGB=true;
                    auto* Pixel=static_cast<FColor*>(Texture->GetPlatformData()->Mips[0].BulkData.Lock(LOCK_READ_WRITE));*Pixel=FColor(210,25,15);Texture->GetPlatformData()->Mips[0].BulkData.Unlock();Texture->UpdateResource();
                    bool Set=false;
                    for(auto Info:Params){FString Name=Info.Name.ToString();UE_LOG(LogTemp,Display,TEXT("RESIDENTIAL_MATERIAL_PARAM %s"),*Name);if(Name.Contains(TEXT("color"),ESearchCase::IgnoreCase)||Name.Contains(TEXT("diffuse"),ESearchCase::IgnoreCase)||Name.Contains(TEXT("albedo"),ESearchCase::IgnoreCase)){MID->SetTextureParameterValue(Info.Name,Texture);Set=true;}}
                    if(!Set&&Params.Num())MID->SetTextureParameterValue(Params[0].Name,Texture);
                    Target->GetStaticMeshComponent()->SetMaterial(0,MID);
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
    if(Review){Verified&=Pass;Phase=90;PhaseTime=0;return;}
    if(FParse::Param(FCommandLine::Get(),TEXT("AuditorTestExit")))FPlatformMisc::RequestExitWithStatus(false,Pass?0:1);
}
void AResidentialScenario::StepVerification(float Dt) {
    PhaseTime+=Dt;if(Age<.6)return;
    if(Age>45){Review=false;Finish(false,TEXT("Scenario verification timeout"));return;}
    auto* P=Player(GetWorld());P->DisableInput(Cast<APlayerController>(P->Controller));
    if(Phase==90){
        if(PhaseTime<1.5)return;
        FString Path;FParse::Value(FCommandLine::Get(),TEXT("AuditorCapture="),Path);
        if(!Capturing){FScreenshotRequest::RequestScreenshot(Path,true,false);Capturing=true;}
        else if(IFileManager::Get().FileExists(*Path)&&FParse::Param(FCommandLine::Get(),TEXT("AuditorTestExit")))FPlatformMisc::RequestExitWithStatus(false,Verified?0:1);
        return;
    }
    if(!Spec){if(Phase==0){SetView(P->Region->SpawnLocation,P->Region->SpawnLocation+P->Region->SpawnRotation.Vector()*500);Phase=1;PhaseTime=0;}else if(PhaseTime>2)Finish(true,TEXT("Clean shared scene"));return;}
    if(Phase==0){SetView(Probe,Center);Phase=1;PhaseTime=0;return;}
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
    else if(Kind==TEXT("proportion"))Finish(Target->GetActorScale3D().Equals(Original.GetScale3D()*(Inject?V(Spec,TEXT("scale")):FVector::OneVector),.01),TEXT("Nonuniform vertical proportion differs from matching dining chairs only in treatment"));
    else if(Kind==TEXT("shadow"))Finish(Inject?(Extra&&Extra->IsHidden()&&Extra->GetStaticMeshComponent()->bCastHiddenShadow&&!Target->GetStaticMeshComponent()->CastShadow):Target->GetStaticMeshComponent()->CastShadow,TEXT("Shadow-only mutation; paired rendered evidence required"));
    else if(Kind==TEXT("plumbing"))Finish(true,TEXT("Continuous plumbing connections authored; labelled endpoints require rendered review"));
    else Finish(false,TEXT("Unknown residential scenario"));
}
