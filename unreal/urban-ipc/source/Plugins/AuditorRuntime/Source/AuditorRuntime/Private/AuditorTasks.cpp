#include "AuditorTasks.h"
#include "AuditorExploration.h"
#include "AuditorPlaytest.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
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

AAuditorTasks::AAuditorTasks()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void AAuditorTasks::BeginPlay()
{
    Super::BeginPlay();
    Testing = FParse::Param(FCommandLine::Get(), TEXT("AuditorTaskTest"));
    TSharedPtr<FJsonObject> Catalog;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(CatalogJson), Catalog) || !Catalog.IsValid())
    { FinishTest(false, TEXT("Invalid catalog")); return; }
    Tasks = Catalog->GetArrayField(TEXT("tasks"));
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

bool AAuditorTasks::Initialize()
{
    if (ActiveId == TEXT("baseline")) return true;
    for (auto Value : Tasks)
        if (Value->AsObject()->GetStringField(TEXT("id")) == ActiveId) { Spec = Value->AsObject(); break; }
    if (!Spec) { FinishTest(false, TEXT("Unknown task ID")); return false; }
    const FString Map = MapFor(Spec->GetStringField(TEXT("region")));
    if (!GetWorld()->GetMapName().EndsWith(FPaths::GetBaseFilename(Map)))
    { OpenTask(ActiveId); return false; }
    Kind = Spec->GetStringField(TEXT("kind"));
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
    if (Kind == TEXT("offset")) Target->AddActorWorldOffset(VectorField(Spec, TEXT("offset")));
    else if (Kind == TEXT("scale")) Target->SetActorScale3D(Original.GetScale3D() * Number(Spec, TEXT("factor"), 1));
    else if (Kind == TEXT("duplicate")) { Added = Clone(Target); Added->AddActorWorldOffset(VectorField(Spec, TEXT("offset"))); }
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
    if (Kind == TEXT("view_cull")) Target->SetActorHiddenInGame(Facing > Number(Spec, TEXT("threshold")));
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

void AAuditorTasks::Interact()
{
    // The baseline offers the same removal action, but never restores the chair.
    const bool BaselineRemoval = ActiveId == TEXT("baseline") && GetWorld()->GetMapName().EndsWith(TEXT("BedroomSuite"));
    if (BaselineRemoval && !Target) Target = FindMesh(TEXT("StaticMeshActor_453"));
    if ((!BaselineRemoval && Kind != TEXT("interact_restore")) || !Target || Target->IsHidden() || RemovedAt >= 0) return;
    const auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
    if (!Pawn || !Pawn->Controller) return;
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
    }
}

void AAuditorTasks::OpenTask(const FString& Id)
{
    FString Map = GetWorld()->GetPackage()->GetName();
    for (auto Value : Tasks)
        if (Value->AsObject()->GetStringField(TEXT("id")) == Id)
            Map = MapFor(Value->AsObject()->GetStringField(TEXT("region")));
    UGameplayStatics::OpenLevel(this, FName(*Map), true, TEXT("Task=") + Id);
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
    if (!Initialized)
    {
        if (!UGameplayStatics::GetPlayerController(this, 0)) return;
        Initialized = Initialize();
        if (Initialized) AuditorExploration::Apply(Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this,0)));
        if (!Initialized) return;
    }
    if (FParse::Param(FCommandLine::Get(), TEXT("AuditorReview")))
    {
        auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
        if (Pawn && Pawn->Controller && Age > 0.5 && TestPhase == 0)
        {
            if (Spec) Pawn->SetActorLocation(VectorField(Spec, TEXT("probe"), Pawn->Region->SpawnLocation));
            const FVector Aim = Added ? Added->GetStaticMeshComponent()->Bounds.Origin : TargetCenter();
            if (Spec) Pawn->Controller->SetControlRotation((Aim - Pawn->Camera->GetComponentLocation()).Rotation());
            TestPhase = 1;
        }
        if (Age > 5 && TestPhase == 1)
        {
            FString Path;
            if (FParse::Value(FCommandLine::Get(), TEXT("AuditorCapture="), Path)) FScreenshotRequest::RequestScreenshot(Path, false, false);
            TestPhase = 2;
        }
        if (Age > 7 && FParse::Param(FCommandLine::Get(), TEXT("AuditorTestExit"))) FPlatformMisc::RequestExit(false);
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
    if (ActiveId == TEXT("baseline")) { FinishTest(true, TEXT("No task injected")); return; }
    auto PlaceView = [&](FVector Position, FVector Aim)
    {
        Pawn->GetCharacterMovement()->StopMovementImmediately();
        Pawn->SetActorLocation(Position);
        Pawn->Controller->SetControlRotation((Aim - Pawn->Camera->GetComponentLocation()).Rotation());
    };
    if (Kind == TEXT("offset")) FinishTest(Target->GetActorLocation().Equals(Original.GetLocation() + VectorField(Spec, TEXT("offset")), 0.1), TEXT("Measured world offset"));
    else if (Kind == TEXT("scale")) FinishTest(Target->GetActorScale3D().Equals(Original.GetScale3D() * Number(Spec, TEXT("factor")), 0.01), TEXT("Measured scale"));
    else if (Kind == TEXT("duplicate")) FinishTest(Added && Added->GetActorLocation().Equals(Original.GetLocation() + VectorField(Spec, TEXT("offset")), 0.1) && Added->GetStaticMeshComponent()->GetStaticMesh() == Target->GetStaticMeshComponent()->GetStaticMesh(), TEXT("Independent overlapping copy"));
    else if (Kind == TEXT("no_collision"))
    {
        // Sweep the actual character-sized capsule through the target in both states.
        FVector Center = TargetCenter();
        Center.Z = Pawn->Region->BoundsMin.Z + 90;
        FVector Extent = Target->GetStaticMeshComponent()->Bounds.BoxExtent;
        FVector Axis = Extent.X < Extent.Y ? FVector(1,0,0) : FVector(0,1,0);
        float Span = (Extent.X < Extent.Y ? Extent.X : Extent.Y) + 50;
        auto HitsTarget = [&]() {
            TArray<FHitResult> Hits;
            FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorTaskCollision), false, Pawn);
            GetWorld()->SweepMultiByChannel(Hits, Center - Axis * Span, Center + Axis * Span, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeCapsule(30,90), Params);
            return Hits.ContainsByPredicate([&](const FHitResult& Hit){return Hit.GetActor() == Target;});
        };
        const bool Removed = !HitsTarget();
        Target->SetActorEnableCollision(true);
        const bool BaselineHit = HitsTarget();
        Target->SetActorEnableCollision(false);
        FinishTest(BaselineCollision && BaselineHit && Removed, TEXT("Baseline capsule hit; injected capsule passes"));
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
