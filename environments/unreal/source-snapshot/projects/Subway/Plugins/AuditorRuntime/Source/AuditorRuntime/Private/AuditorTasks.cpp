#include "AuditorTasks.h"
#include "AuditorPlaytest.h"
#include "AuditorResidentialRevision.h"
#include "ResidentialScenario.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/TextRenderActor.h"
#include "Math/RotationMatrix.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMeshActor.h"
#include "UnrealClient.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "HAL/FileManager.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace {
FVector VectorField(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Name, FVector Fallback = FVector::ZeroVector)
{
    const TArray<TSharedPtr<FJsonValue>>* A;
    if (!Obj->TryGetArrayField(Name, A) || A->Num() != 3) return Fallback;
    return FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber());
}
double Number(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Name, double Fallback = 0)
{
    double V; return Obj->TryGetNumberField(Name, V) ? V : Fallback;
}
FString MapFor(const FString& Region)
{
    if (Region == TEXT("kitchen_dining")) return TEXT("/Game/Auditor/Regions/KitchenDining");
    if (Region == TEXT("bedroom_suite")) return TEXT("/Game/Auditor/Regions/BedroomSuite");
    return TEXT("/Game/Auditor/Regions/LivingRoom");
}
}

#include "ConfigurationPose.inl"

AAuditorTasks::AAuditorTasks()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void AAuditorTasks::BeginPlay()
{
    Super::BeginPlay();
    Testing = FParse::Param(FCommandLine::Get(), TEXT("AuditorTaskTest")) || FParse::Param(FCommandLine::Get(), TEXT("AuditorEscalatorBaselineTest"));
    TSharedPtr<FJsonObject> Catalog;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(CatalogJson), Catalog) || !Catalog.IsValid())
    { FinishTest(false, TEXT("Invalid catalog")); return; }
    Tasks = Catalog->GetArrayField(TEXT("tasks"));
    ApplyResidentialRevision(GetWorld(), Tasks);
    OperatingFan = FindMesh(TEXT("VentilationRotor"));
    FString Requested;
    const AGameModeBase* Mode = GetWorld()->GetAuthGameMode();
    if (Mode) Requested = UGameplayStatics::ParseOption(Mode->OptionsString, TEXT("Task"));
    if (Requested.IsEmpty()) FParse::Value(FCommandLine::Get(), TEXT("AuditorTask="), Requested);
    if (!Requested.IsEmpty()) ActiveId = Requested;
}

AStaticMeshActor* AAuditorTasks::FindMesh(const FString& Name) const
{
    const FName Tag(*(TEXT("auditor_actor:") + Name));
    for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
        if (It->ActorHasTag(Tag)) return *It;
    return nullptr;
}

AStaticMeshActor* AAuditorTasks::Clone(AStaticMeshActor* Source)
{
    if (!Source) return nullptr;
    AStaticMeshActor* Copy = GetWorld()->SpawnActor<AStaticMeshActor>();
    Copy->SetMobility(EComponentMobility::Movable);
    auto* Mesh = Copy->GetStaticMeshComponent();
    auto* OriginalMesh = Source->GetStaticMeshComponent();
    Mesh->SetStaticMesh(OriginalMesh->GetStaticMesh());
    for (int32 I = 0; I < OriginalMesh->GetNumMaterials(); ++I) Mesh->SetMaterial(I, OriginalMesh->GetMaterial(I));
    Mesh->SetCollisionProfileName(OriginalMesh->GetCollisionProfileName());
    Copy->SetActorTransform(Source->GetActorTransform());
    return Copy;
}

FVector AAuditorTasks::TargetCenter() const
{
    return Target ? Target->GetStaticMeshComponent()->Bounds.Origin : FVector::ZeroVector;
}

void AAuditorTasks::ApplyMaterial()
{
    if (!Target || !ErrorMaterial) return;
    auto* Mesh = Target->GetStaticMeshComponent();
    for (int32 I = 0; I < Mesh->GetNumMaterials(); ++I) Mesh->SetMaterial(I, ErrorMaterial);
    Changed = true;
}

void AAuditorTasks::OnContact(UPrimitiveComponent*, AActor* Other, UPrimitiveComponent*, FVector, const FHitResult&)
{
    if (Kind == TEXT("contact_jitter") && Other == Target.Get() && ContactAt < 0)
    { ContactAt = Age; Changed = true; }
}

void AAuditorTasks::SetHose(const FString& Name, FVector Start, FVector End)
{
    if (auto* Hose = FindMesh(Name))
    {
        Hose->SetMobility(EComponentMobility::Movable);
        Hose->SetActorLocation((Start+End)*0.5);
        Hose->SetActorRotation(FRotationMatrix::MakeFromZ(End-Start).Rotator());
        Hose->SetActorScale3D(FVector(.06,.06,FVector::Dist(Start,End)/100));
    }
}

bool AAuditorTasks::Initialize()
{
    if (ActiveId == TEXT("baseline"))
    {
        ConfigureEscalators(false);
        if (Tasks.Num() && Tasks[0]->AsObject()->HasField(TEXT("scenario")))
        {
            ResidentialScenario = GetWorld()->SpawnActor<AResidentialScenario>();
            return ResidentialScenario->Configure(this, nullptr);
        }
        return true;
    }
    for (auto Value : Tasks)
        if (Value->AsObject()->GetStringField(TEXT("id")) == ActiveId) { Spec = Value->AsObject(); break; }
    if (!Spec) { FinishTest(false, TEXT("Unknown task ID")); return false; }
    FString Map;
    if (!Spec->TryGetStringField(TEXT("map"), Map)) Map = MapFor(Spec->GetStringField(TEXT("region")));
    if (!GetWorld()->GetMapName().EndsWith(FPaths::GetBaseFilename(Map)))
    { OpenTask(ActiveId); return false; }
    Kind = Spec->GetStringField(TEXT("kind"));
    if (Spec->HasField(TEXT("scenario")))
    {
        ResidentialScenario = GetWorld()->SpawnActor<AResidentialScenario>();
        const bool Ready = ResidentialScenario->Configure(this, Spec);
        if (Ready) UE_LOG(LogTemp, Display, TEXT("AUDITOR_TASK_READY id=%s map=%s kind=%s"), *ActiveId, *GetWorld()->GetMapName(), *Kind);
        return Ready;
    }
    const FString Name = Spec->GetStringField(TEXT("target"));
    if (!Name.IsEmpty())
    {
        Target = FindMesh(Name);
        if (!Target) { FinishTest(false, TEXT("Missing target: ") + Name); return false; }
        Original = Target->GetActorTransform();
        OriginalCenter = TargetCenter();
        BaselineCollision = Target->GetActorEnableCollision() && Target->GetStaticMeshComponent()->GetCollisionResponseToChannel(ECC_Pawn) == ECR_Block
            && Target->GetStaticMeshComponent()->GetCollisionEnabled() != ECollisionEnabled::NoCollision;
        Target->SetMobility(EComponentMobility::Movable);
    }
    if (Kind == TEXT("configuration_pose")) ApplyConfigurationPose(Target,Spec);
    else if (Kind == TEXT("offset")) Target->AddActorWorldOffset(VectorField(Spec, TEXT("offset")));
    else if (Kind == TEXT("scale")) Target->SetActorScale3D(Original.GetScale3D() * Number(Spec, TEXT("factor"), 1));
    else if (Kind == TEXT("duplicate"))
    {
        Added = Clone(Target);
        Added->AddActorWorldRotation(FRotator(0, Number(Spec, TEXT("yaw")), 0));
        Added->AddActorWorldOffset(VectorField(Spec, TEXT("offset")));
    }
    else if (Kind == TEXT("tilt"))
    {
        Target->AddActorWorldRotation(FRotator(Number(Spec, TEXT("pitch")), 0, 0));
        Target->AddActorWorldOffset(OriginalCenter + VectorField(Spec, TEXT("offset")) - TargetCenter());
    }
    else if (Kind == TEXT("axis_scale")) Target->SetActorScale3D(Original.GetScale3D()*VectorField(Spec,TEXT("scale")));
    else if (Kind == TEXT("contact_jitter"))
    {
        if (auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0)))
            Pawn->GetCapsuleComponent()->OnComponentHit.AddDynamic(this,&AAuditorTasks::OnContact);
    }
    else if (Kind == TEXT("shadow_offset"))
    {
        Added=Clone(Target); Added->SetActorEnableCollision(false);
        Added->GetStaticMeshComponent()->SetCastHiddenShadow(true);
        Added->SetActorHiddenInGame(true);
        Added->AddActorWorldOffset(VectorField(Spec,TEXT("offset")));
        Target->GetStaticMeshComponent()->SetCastShadow(false);
    }
    else if (Kind == TEXT("cross_connect"))
    {
        SetHose(TEXT("HoseMiddleA"),FVector(-135,5335,620),FVector(135,5335,495));
        SetHose(TEXT("HoseBottomA"),FVector(135,5335,495),FVector(135,5367,495));
        SetHose(TEXT("HoseMiddleB"),FVector(135,5315,620),FVector(-135,5315,495));
        SetHose(TEXT("HoseBottomB"),FVector(-135,5315,495),FVector(-135,5367,495));
    }
    else if (Kind == TEXT("escalators_same_direction"))
    {
        if (!ConfigureEscalators(true)) { FinishTest(false,TEXT("Expected eight authored escalators")); return false; }
        if (auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0)))
        {
            Pawn->SetActorLocation(VectorField(Spec,TEXT("probe")));
            if (Pawn->Controller) Pawn->Controller->SetControlRotation((VectorField(Spec,TEXT("review_aim"))-Pawn->Camera->GetComponentLocation()).Rotation());
        }
    }
    else if (Kind == TEXT("false_exit"))
    {
        for (TActorIterator<ATextRenderActor> It(GetWorld());It;++It)
            if (It->ActorHasTag(TEXT("auditor_text:ServiceSign")))
                It->GetTextRender()->SetText(FText::FromString(TEXT("EXIT / OPEN PASSAGE")));
    }
    else if (Kind == TEXT("no_collision")) Target->SetActorEnableCollision(false);
    else if (Kind == TEXT("blocker"))
    {
        Blocker = NewObject<UBoxComponent>(this);
        AddInstanceComponent(Blocker);
        Blocker->SetupAttachment(RootComponent);
        Blocker->SetBoxExtent(VectorField(Spec, TEXT("extent")));
        Blocker->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        Blocker->SetCollisionResponseToAllChannels(ECR_Ignore);
        Blocker->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
        Blocker->SetHiddenInGame(true);
        Blocker->SetCanEverAffectNavigation(false);
        Blocker->RegisterComponent();
        Blocker->SetWorldLocation(VectorField(Spec, TEXT("position")));
    }
    else if (Kind == TEXT("material")) ApplyMaterial();
    else if (Kind == TEXT("distance_scale"))
    {
        // Keep the baseline collision surface; only the rendered LOD surrogate changes.
        Added = Clone(Target);
        Added->SetActorEnableCollision(false);
        Target->SetActorHiddenInGame(true);
    }
    else if (Kind == TEXT("semantic_add") || Kind == TEXT("semantic_replace"))
    {
        AStaticMeshActor* Source = Kind == TEXT("semantic_add") ? Target.Get() : FindMesh(Spec->GetStringField(TEXT("source")));
        Added = Clone(Source);
        if (!Added) { FinishTest(false, TEXT("Missing semantic source")); return false; }
        if (Kind == TEXT("semantic_add"))
        {
            Added->SetActorLocation(VectorField(Spec, TEXT("position")));
            Added->SetActorRotation(FRotator(0, Number(Spec, TEXT("yaw")), 0));
            if (ActiveId == TEXT("S20")) Added->Tags.Add(TEXT("auditor_actor:PlatformPrivateCar"));
        }
        else
        {
            // Align actual bounding-box bottoms, not differing asset pivots.
            const auto Bounds = Target->GetStaticMeshComponent()->Bounds;
            const FVector Bottom(Bounds.Origin.X, Bounds.Origin.Y, Bounds.Origin.Z - Bounds.BoxExtent.Z);
            Added->SetActorLocation(Original.GetLocation());
            const auto AddedBounds = Added->GetStaticMeshComponent()->Bounds;
            Added->AddActorWorldOffset(Bottom - FVector(AddedBounds.Origin.X, AddedBounds.Origin.Y, AddedBounds.Origin.Z - AddedBounds.BoxExtent.Z));
            Target->SetActorHiddenInGame(true);
            Target->SetActorEnableCollision(false);
        }
    }
    if (Kind.StartsWith(TEXT("semantic_")) && Added)
    {
        // Asset pivots differ. Seat the new object's bounding bottom on the actual
        // supporting surface so a semantic task does not also inject penetration.
        const auto Bounds = Added->GetStaticMeshComponent()->Bounds;
        const FVector Bottom(Bounds.Origin.X, Bounds.Origin.Y, Bounds.Origin.Z - Bounds.BoxExtent.Z);
        FHitResult Support;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorSemanticPlacement), true, Added);
        if (Kind == TEXT("semantic_replace")) Params.AddIgnoredActor(Target);
        GetWorld()->LineTraceSingleByChannel(Support, Bottom + FVector(0,0,20), Bottom - FVector(0,0,40), ECC_Visibility, Params);
        if (Support.bBlockingHit) Added->AddActorWorldOffset(FVector(0,0,Support.ImpactPoint.Z - Bottom.Z));
    }
    UE_LOG(LogTemp, Display, TEXT("AUDITOR_TASK_READY id=%s map=%s kind=%s"), *ActiveId, *GetWorld()->GetMapName(), *Kind);
    return true;
}

void AAuditorTasks::UpdateEffect()
{
    AAuditorCharacter* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
    if (!Pawn || !Target || !Pawn->Controller) return;
    const FVector Eye = Pawn->Camera->GetComponentLocation();
    const FVector Delta = TargetCenter() - Eye;
    const float Facing = FVector::DotProduct(Pawn->Controller->GetControlRotation().Vector(), Delta.GetSafeNormal());
    const float Distance = FVector::Dist2D(Pawn->GetActorLocation(), TargetCenter());
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorVisibility), true, Pawn);
    GetWorld()->LineTraceSingleByChannel(Hit, Eye, TargetCenter(), ECC_Visibility, Params);
    const bool Visible = Facing > 0.8 && Delta.Size() < 650 && (!Hit.bBlockingHit || Hit.GetActor() == Target || Hit.GetActor() == Added);
    if (Kind == TEXT("contact_jitter") && ContactAt >= 0)
        Target->SetActorLocation(Original.GetLocation()+FVector(0,FMath::Sin((Age-ContactAt)*40)*8,0));
    else if (Kind == TEXT("return_reverse"))
    {
        if (Visible) Seen = true;
        if (Seen && Facing < 0 && !Changed) { Changed = true; FanReversed = true; }
    }
    else if (Kind == TEXT("view_cull")) Target->SetActorHiddenInGame(Facing > Number(Spec, TEXT("threshold")));
    else if (Kind == TEXT("distance_cull")) Target->SetActorHiddenInGame(Distance > Number(Spec, TEXT("threshold")));
    else if (Kind == TEXT("distance_scale"))
        Added->SetActorScale3D(Original.GetScale3D() * (Distance > Number(Spec, TEXT("threshold")) ? Number(Spec, TEXT("factor")) : 1));
    else if (Kind == TEXT("lookaway_hide") || Kind == TEXT("lookaway_material"))
    {
        if (Visible) Seen = true;
        if (Seen && Facing < 0 && !Changed)
        {
            if (Kind == TEXT("lookaway_hide")) { Target->SetActorHiddenInGame(true); Target->SetActorEnableCollision(false); Changed = true; }
            else ApplyMaterial();
        }
    }
    else if (Kind == TEXT("return_move"))
    {
        if (Distance < Number(Spec, TEXT("near")) && Visible) NearSeen = true;
        if (NearSeen && Distance > Number(Spec, TEXT("far")) && Facing < 0) Left = true;
        if (Left && Distance < Number(Spec, TEXT("near")) && !Changed)
        { Target->AddActorWorldOffset(VectorField(Spec, TEXT("offset"))); Changed = true; }
    }
    else if (Kind == TEXT("interact_restore") && RemovedAt >= 0 && Age - RemovedAt >= Number(Spec, TEXT("delay")))
    { Target->SetActorHiddenInGame(false); Target->SetActorEnableCollision(true); Changed = true; RemovedAt = -1; }
}

FString AAuditorTasks::Interact()
{
    if (ResidentialScenario.IsValid()) return ResidentialScenario->Interact();
    // Clean maps offer the same removal action without spontaneous restoration.
    bool BaselineRemoval = false;
    if (ActiveId == TEXT("baseline"))
    {
        for (const auto& Value : Tasks)
        {
            const auto Task = Value->AsObject();
            FString Map;
            if (!Task->TryGetStringField(TEXT("map"), Map)) Map = MapFor(Task->GetStringField(TEXT("region")));
            if (Task->GetStringField(TEXT("kind")) == TEXT("interact_restore") && GetWorld()->GetMapName().EndsWith(FPaths::GetBaseFilename(Map)))
            {
                BaselineRemoval = true;
                if (!Target) Target = FindMesh(Task->GetStringField(TEXT("target")));
                break;
            }
        }
    }
    if ((!BaselineRemoval && Kind != TEXT("interact_restore")) || !Target) return TEXT("not_interactable");
    if (Target->IsHidden() || RemovedAt >= 0) return TEXT("no_target");
    const auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
    if (!Pawn || !Pawn->Controller) return TEXT("not_ready");
    const FVector Eye = Pawn->Camera->GetComponentLocation();
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorInteraction), true, Pawn);
    GetWorld()->LineTraceSingleByChannel(Hit, Eye, Eye + Pawn->Controller->GetControlRotation().Vector() * 250, ECC_Visibility, Params);
    if (Hit.GetActor() == Target)
    {
        Target->SetActorHiddenInGame(true);
        Target->SetActorEnableCollision(false);
        RemovedAt = BaselineRemoval ? -1 : Age;
        Changed = false;
        return TEXT("interacted");
    }
    if (!Hit.GetActor())
    {
        GetWorld()->LineTraceSingleByChannel(Hit, Eye, Eye + Pawn->Controller->GetControlRotation().Vector() * 2000, ECC_Visibility, Params);
        return Hit.GetActor() == Target ? TEXT("out_of_reach") : TEXT("no_target");
    }
    return TEXT("not_interactable");
}

void AAuditorTasks::OpenTask(const FString& Id)
{
    FString Map = GetWorld()->GetPackage()->GetName();
    for (auto Value : Tasks)
        if (Value->AsObject()->GetStringField(TEXT("id")) == Id)
        {
            if (!Value->AsObject()->TryGetStringField(TEXT("map"), Map))
                Map = MapFor(Value->AsObject()->GetStringField(TEXT("region")));
        }
    UGameplayStatics::OpenLevel(this, FName(*Map), true, TEXT("Task=") + Id);
}
FString AAuditorTasks::TaskIdAt(int32 Index) const
{
    return Tasks.IsValidIndex(Index) ? Tasks[Index]->AsObject()->GetStringField(TEXT("id")) : FString();
}

void AAuditorTasks::Cycle(int32 Direction)
{
    if (Tasks.IsEmpty()) return;
    int32 Index = Direction > 0 ? -1 : 0;
    for (int32 I = 0; I < Tasks.Num(); ++I)
        if (Tasks[I]->AsObject()->GetStringField(TEXT("id")) == ActiveId) Index = I;
    OpenTask(Tasks[(Index + Direction + Tasks.Num()) % Tasks.Num()]->AsObject()->GetStringField(TEXT("id")));
}
void AAuditorTasks::Restart() { OpenTask(ActiveId); }

void AAuditorTasks::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    Age += DeltaSeconds;
    if (OperatingFan)
        OperatingFan->AddActorWorldRotation(FRotator((FanReversed ? -90 : 90)*DeltaSeconds,0,0));
    if (!Initialized)
    {
        if (!UGameplayStatics::GetPlayerController(this, 0)) return;
        Initialized = Initialize();
        if (!Initialized) return;
    }
    if (ResidentialScenario.IsValid()) return;
    if (FParse::Param(FCommandLine::Get(), TEXT("AuditorReview")))
    {
        auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
        if (Pawn && Pawn->Controller && Age > 0.5 && TestPhase == 0)
        {
            // A mouse moving in another app must not alter automated review views.
            Pawn->DisableInput(Cast<APlayerController>(Pawn->Controller));
            Pawn->GetCharacterMovement()->StopMovementImmediately();
            auto ViewSpec = Spec;
            AStaticMeshActor* Reference = nullptr;
            FString ReferenceId;
            if (!ViewSpec && FParse::Value(FCommandLine::Get(), TEXT("AuditorReviewReference="), ReferenceId))
                for (auto Value : Tasks)
                    if (Value->AsObject()->GetStringField(TEXT("id")) == ReferenceId)
                    { ViewSpec = Value->AsObject(); Reference = FindMesh(ViewSpec->GetStringField(TEXT("target"))); break; }
            Pawn->SetActorLocation(ViewSpec ? VectorField(ViewSpec, TEXT("probe"), Pawn->Region->SpawnLocation) : Pawn->Region->SpawnLocation);
            FVector Aim = Reference ? Reference->GetStaticMeshComponent()->Bounds.Origin : (Added ? Added->GetStaticMeshComponent()->Bounds.Origin : TargetCenter());
            if (ViewSpec) Aim = VectorField(ViewSpec,TEXT("review_aim"),Aim);
            FRotator Rotation = ViewSpec ? (Aim - Pawn->Camera->GetComponentLocation()).Rotation() : Pawn->Region->SpawnRotation;
            FParse::Value(FCommandLine::Get(), TEXT("AuditorReviewYaw="), Rotation.Yaw);
            FParse::Value(FCommandLine::Get(), TEXT("AuditorReviewPitch="), Rotation.Pitch);
            Pawn->Controller->SetControlRotation(Rotation);
            TestPhase = 1;
        }
        if (Age > 5 && TestPhase == 1)
        {
            FString Path;
            if (FParse::Value(FCommandLine::Get(), TEXT("AuditorCapture="), Path)) FScreenshotRequest::RequestScreenshot(Path, true, false);
            ReviewCaptureAge = Age;
            TestPhase = 2;
        }
        if (TestPhase == 2 && FParse::Param(FCommandLine::Get(), TEXT("AuditorTestExit")))
        {
            FString Path;
            FParse::Value(FCommandLine::Get(), TEXT("AuditorCapture="), Path);
            if (IFileManager::Get().FileExists(*Path)) FPlatformMisc::RequestExit(false);
            else if (Age - ReviewCaptureAge > 60) FinishTest(false, TEXT("Review screenshot was not written"));
        }
    }
    UpdateEffect();
    if (Testing) { PhaseAge += DeltaSeconds; TestStep(); }
}

void AAuditorTasks::FinishTest(bool Passed, const FString& Detail)
{
    UE_LOG(LogTemp, Display, TEXT("AUDITOR_TASK_TEST %s id=%s detail=%s"), Passed ? TEXT("PASS") : TEXT("FAIL"), *ActiveId, *Detail);
    Testing = false;
    if (FParse::Param(FCommandLine::Get(), TEXT("AuditorTestExit"))) FPlatformMisc::RequestExitWithStatus(false, Passed ? 0 : 1);
}

void AAuditorTasks::TestStep()
{
    auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
    if (!Pawn || !Pawn->Controller || Age < 0.5) return;
    if (Age > 15) { FinishTest(false, TEXT("Behavior timed out")); return; }
    if (ActiveId == TEXT("baseline"))
    {
        if (FParse::Param(FCommandLine::Get(),TEXT("AuditorEscalatorBaselineTest"))) TestEscalators(false);
        else FinishTest(true, TEXT("No task injected"));
        return;
    }
    if (Kind == TEXT("escalators_same_direction")) { TestEscalators(true); return; }
    auto PlaceView = [&](FVector Position, FVector Aim)
    {
        Pawn->GetCharacterMovement()->StopMovementImmediately();
        Pawn->SetActorLocation(Position);
        Pawn->Controller->SetControlRotation((Aim - Pawn->Camera->GetComponentLocation()).Rotation());
    };
    if (Kind == TEXT("offset")) FinishTest(Target->GetActorLocation().Equals(Original.GetLocation() + VectorField(Spec, TEXT("offset")), 0.1), TEXT("Measured world offset"));
    else if (Kind == TEXT("scale")) FinishTest(Target->GetActorScale3D().Equals(Original.GetScale3D() * Number(Spec, TEXT("factor")), 0.01), TEXT("Measured scale"));
    else if (Kind == TEXT("axis_scale")) FinishTest(Target->GetActorScale3D().Equals(Original.GetScale3D()*VectorField(Spec,TEXT("scale")),0.01),TEXT("Adult passenger seat raised to three times its standard seat height"));
    else if (Kind == TEXT("shadow_offset")) FinishTest(Added && Added->IsHidden() && !Added->GetActorEnableCollision() && Added->GetStaticMeshComponent()->bCastHiddenShadow && !Target->GetStaticMeshComponent()->CastShadow && Added->GetActorLocation().Equals(Original.GetLocation()+VectorField(Spec,TEXT("offset")),.1),TEXT("Visible geometry unchanged; hidden shadow caster displaced (render review required)"));
    else if (Kind == TEXT("cross_connect"))
    {
        auto* A=FindMesh(TEXT("HoseMiddleA")); auto* B=FindMesh(TEXT("HoseMiddleB"));
        auto Endpoints=[](AStaticMeshActor* Pipe,FVector Start,FVector End) {
            const FVector Half=Pipe->GetActorUpVector()*Pipe->GetActorScale3D().Z*50;
            return (Pipe->GetActorLocation()-Half).Equals(Start,.1) && (Pipe->GetActorLocation()+Half).Equals(End,.1);
        };
        FinishTest(A && B && Endpoints(A,FVector(-135,5335,620),FVector(135,5335,495)) && Endpoints(B,FVector(135,5315,620),FVector(-135,5315,495)) && Endpoints(FindMesh(TEXT("HoseBottomA")),FVector(135,5335,495),FVector(135,5367,495)) && Endpoints(FindMesh(TEXT("HoseBottomB")),FVector(-135,5315,495),FVector(-135,5367,495)),TEXT("Continuous hoses connect labelled clean-water outlet to waste-water inlet and vice versa"));
    }
    else if (Kind == TEXT("false_exit"))
    {
        bool Sign=false;
        for (TActorIterator<ATextRenderActor> It(GetWorld());It;++It)
            if (It->ActorHasTag(TEXT("auditor_text:ServiceSign"))) Sign=It->GetTextRender()->Text.ToString()==TEXT("EXIT / OPEN PASSAGE");
        FHitResult Hit; FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorFalseExit),false,Pawn);
        GetWorld()->LineTraceSingleByChannel(Hit,FVector(300,1100,100),FVector(300,1250,100),ECC_Visibility,Params);
        FinishTest(Sign && Hit.bBlockingHit && Hit.GetActor()==FindMesh(TEXT("SealedServicePanel")),TEXT("Official exit sign promises open passage through visibly sealed solid panel"));
    }
    else if (Kind == TEXT("contact_jitter"))
    {
        if (TestPhase==0) { PlaceView(VectorField(Spec,TEXT("probe")),OriginalCenter); TestPhase=1; PhaseAge=0; }
        else if (TestPhase==1)
        {
            if (ContactAt<0) Pawn->AddMovementInput((OriginalCenter-Pawn->GetActorLocation()).GetSafeNormal2D(),1);
            else { TestFirstState=BaselineCollision; PlaceView(VectorField(Spec,TEXT("probe")),OriginalCenter); TestPosition=Target->GetActorLocation(); TestSample=0; TestPhase=2;PhaseAge=0; }
        }
        else if (TestPhase>=2)
        {
            TestSample=FMath::Max(TestSample,float(FVector::Dist(Target->GetActorLocation(),TestPosition)));
            if(PhaseAge>.8)
            {
                if(TestPhase==2){TestFirstState &= TestSample>5;TestPosition=Target->GetActorLocation();TestSample=0;TestPhase=3;PhaseAge=0;}
                else FinishTest(TestFirstState && ContactAt>=0 && TestSample>5,TEXT("Actual character collision starts sustained jitter; motion continues after contact ends"));
            }
        }
    }
    else if (Kind == TEXT("return_reverse"))
    {
        auto Angle=[&](){ return FMath::RadiansToDegrees(FMath::Atan2(Target->GetActorForwardVector().Z,Target->GetActorForwardVector().X)); };
        if(TestPhase==0){PlaceView(VectorField(Spec,TEXT("probe")),OriginalCenter);TestSample=Angle();TestPhase=1;PhaseAge=0;}
        else if(TestPhase==1 && PhaseAge>.4){TestFirstState=Seen && !Changed && FMath::FindDeltaAngleDegrees(TestSample,Angle()) > 20;Pawn->Controller->SetControlRotation(Pawn->Controller->GetControlRotation()+FRotator(0,180,0));TestPhase=2;PhaseAge=0;}
        else if(TestPhase==2 && PhaseAge>.2){PlaceView(VectorField(Spec,TEXT("probe")),OriginalCenter);TestSample=Angle();TestPhase=3;PhaseAge=0;}
        else if(TestPhase==3 && PhaseAge>.4)FinishTest(TestFirstState && FanReversed && FMath::FindDeltaAngleDegrees(TestSample,Angle()) < -20,TEXT("Measured continuous fan rotation before looking away; persistent reverse rotation on return without control input"));
    }
    else if (Kind == TEXT("configuration_pose")) { FString Detail;const bool Pass=CheckConfigurationPose(Target,Original,Spec,Detail);FinishTest(Pass,Detail); }
    else if (Kind == TEXT("tilt"))
    {
        const auto Bounds = Target->GetStaticMeshComponent()->Bounds;
        const float Floor = Pawn->Region->BoundsMin.Z;
        const bool CutsFloor = Bounds.Origin.Z-Bounds.BoxExtent.Z < Floor-10 && Bounds.Origin.Z+Bounds.BoxExtent.Z > Floor+30;
        FinishTest(CutsFloor && TargetCenter().Equals(OriginalCenter+VectorField(Spec,TEXT("offset")),0.1) && !Target->GetActorQuat().Equals(Original.GetRotation(),0.1), TEXT("Tilted chair crosses the floor plane by more than 10 cm"));
    }
    else if (Kind == TEXT("duplicate")) FinishTest(Added && Added->GetActorLocation().Equals(Original.GetLocation() + VectorField(Spec, TEXT("offset")), 0.1) && Added->GetStaticMeshComponent()->GetStaticMesh() == Target->GetStaticMeshComponent()->GetStaticMesh(), TEXT("Independent overlapping copy"));
    else if (Kind == TEXT("no_collision"))
    {
        // Sweep the actual character-sized capsule through the target in both states.
        FVector Center = TargetCenter();
        Center.Z = Pawn->GetActorLocation().Z;
        FVector Extent = Target->GetStaticMeshComponent()->Bounds.BoxExtent;
        FVector Axis = Extent.X < Extent.Y ? FVector(1,0,0) : FVector(0,1,0);
        float Span = (Extent.X < Extent.Y ? Extent.X : Extent.Y) + 50;
        auto HitsTarget = [&]() {
            TArray<FHitResult> Hits;
            FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorTaskCollision), false, Pawn);
            // Isolate the target for the before/after capsule test; floors and
            // nearby clutter can otherwise terminate the sweep before it arrives.
            for (TActorIterator<AActor> It(GetWorld()); It; ++It)
                if (*It != Target.Get()) Params.AddIgnoredActor(*It);
            GetWorld()->SweepMultiByChannel(Hits, Center - Axis * Span, Center + Axis * Span, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeCapsule(30,90), Params);
            return Hits.ContainsByPredicate([&](const FHitResult& Hit){return Hit.GetActor() == Target;});
        };
        const bool Removed = !HitsTarget();
        Target->SetActorEnableCollision(true);
        const bool BaselineHit = HitsTarget();
        Target->SetActorEnableCollision(false);
        FinishTest(BaselineCollision && BaselineHit && Removed, TEXT("Target capsule hits baseline geometry; injected target permits passage"));
    }
    else if (Kind == TEXT("blocker"))
    {
        FVector C = VectorField(Spec, TEXT("position"));
        FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorTaskBlocker), false, Pawn);
        auto Sweep = [&](){ TArray<FHitResult> Hits; GetWorld()->SweepMultiByChannel(Hits,C-FVector(0,65,0),C+FVector(0,65,0),FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(30,90),Params); return Hits; };
        const auto With = Sweep();
        Blocker->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        const auto Without = Sweep();
        Blocker->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        const bool AddedHit = With.ContainsByPredicate([&](const FHitResult& H){return H.GetComponent()==Blocker;});
        FinishTest(AddedHit && !Without.ContainsByPredicate([](const FHitResult& H){return H.bBlockingHit;}), TEXT("Open baseline passage; invisible injected blocker"));
    }
    else if (Kind == TEXT("material")) FinishTest(ErrorMaterial && Target->GetStaticMeshComponent()->GetMaterial(0) == ErrorMaterial, TEXT("Material replaced"));
    else if (Kind.StartsWith(TEXT("semantic_")))
    {
        FHitResult Hit;
        auto Bounds = Added->GetStaticMeshComponent()->Bounds;
        FVector Bottom(Bounds.Origin.X,Bounds.Origin.Y,Bounds.Origin.Z-Bounds.BoxExtent.Z);
        FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorTaskSupport), true, Added);
        if (Kind == TEXT("semantic_replace")) Params.AddIgnoredActor(Target);
        GetWorld()->LineTraceSingleByChannel(Hit, Bottom+FVector(0,0,4), Bottom-FVector(0,0,15), ECC_Visibility, Params);
        UE_LOG(LogTemp, Display, TEXT("AUDITOR_SEMANTIC_SUPPORT bottom=%s hit=%s distance=%.1f"), *Bottom.ToString(), *GetNameSafe(Hit.GetActor()), Hit.Distance);
        FinishTest(Added && !Added->IsHidden() && Hit.bBlockingHit && FMath::Abs(Hit.Distance - 4) < 1 && (!Kind.EndsWith(TEXT("replace")) || Target->IsHidden()), TEXT("Replacement/addition exists and has support beneath it"));
    }
    else if (TestPhase == 0)
    {
        // Fixed reachable probe positions are authored per task; rendering tests use
        // real view/distance conditions, never direct writes to the effect state.
        FVector Probe = VectorField(Spec, TEXT("probe"), Pawn->Region->SpawnLocation);
        PlaceView(Probe, OriginalCenter);
        TestPhase = 1; PhaseAge = 0;
    }
    else if (TestPhase == 1 && PhaseAge > 0.2)
    {
        if (Kind == TEXT("view_cull"))
        { TestFirstState = Target->IsHidden(); Pawn->Controller->SetControlRotation(Pawn->Controller->GetControlRotation()+FRotator(0,40,0)); }
        else if (Kind == TEXT("distance_cull") || Kind == TEXT("distance_scale"))
        {
            TestFirstState = Kind == TEXT("distance_cull") ? !Target->IsHidden() : Added->GetActorScale3D().Equals(Original.GetScale3D(),0.01);
            PlaceView(VectorField(Spec,TEXT("far_probe")),OriginalCenter);
        }
        else if (Kind == TEXT("lookaway_hide") || Kind == TEXT("lookaway_material"))
        { TestFirstState = Seen && !Changed; Pawn->Controller->SetControlRotation(Pawn->Controller->GetControlRotation()+FRotator(0,180,0)); }
        else if (Kind == TEXT("return_move"))
        { TestFirstState = NearSeen && !Changed; PlaceView(VectorField(Spec,TEXT("far_probe")),OriginalCenter); Pawn->Controller->SetControlRotation(Pawn->Controller->GetControlRotation()+FRotator(0,180,0)); }
        else if (Kind == TEXT("interact_restore")) { Interact(); TestFirstState = Target->IsHidden() && RemovedAt >= 0; }
        TestPhase = 2; PhaseAge = 0;
    }
    else if (TestPhase == 2 && PhaseAge > 0.25)
    {
        if (Kind == TEXT("return_move")) { TestFirstState &= Left && !Changed; PlaceView(VectorField(Spec,TEXT("probe")),OriginalCenter); TestPhase=3;PhaseAge=0; }
        else if (Kind == TEXT("interact_restore")) { if (PhaseAge > Number(Spec,TEXT("delay"))+0.2) FinishTest(TestFirstState && Changed && !Target->IsHidden() && Target->GetActorEnableCollision(),TEXT("Real interaction hides, timed state restores")); }
        else if (Kind == TEXT("view_cull")) FinishTest(TestFirstState && !Target->IsHidden(),TEXT("Center-view culling and peripheral recovery"));
        else if (Kind == TEXT("distance_cull")) FinishTest(TestFirstState && Target->IsHidden(),TEXT("Near visible, far culled"));
        else if (Kind == TEXT("distance_scale")) FinishTest(TestFirstState && Added->GetActorScale3D().Equals(Original.GetScale3D()*Number(Spec,TEXT("factor")),0.01),TEXT("Near/far visual shape change"));
        else if (Kind == TEXT("lookaway_hide")) FinishTest(TestFirstState && Changed && Target->IsHidden(),TEXT("Observed, turned away, permanently disappeared"));
        else if (Kind == TEXT("lookaway_material")) FinishTest(TestFirstState && Changed && Target->GetStaticMeshComponent()->GetMaterial(0)==ErrorMaterial,TEXT("Observed, turned away, material changed"));
    }
    else if (TestPhase == 3 && PhaseAge > 0.2)
        FinishTest(TestFirstState && Changed && Target->GetActorLocation().Equals(Original.GetLocation()+VectorField(Spec,TEXT("offset")),0.1),TEXT("Approach, leave, return changed position"));
}
