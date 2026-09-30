#include "AuditorStateScenario.h"
#include "AuditorExploration.h"
#include "Components/MeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"

AAuditorStateScenario::AAuditorStateScenario()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}
void AAuditorStateScenario::BeginPlay()
{
    Super::BeginPlay();
    if (!IsValid(TargetActor)) { UE_LOG(LogTemp, Error, TEXT("AUDITOR_STATE_INVALID_TARGET id=%s"), *TaskId); SetActorTickEnabled(false); return; }
    if (Effect == EAuditorScenarioEffect::TransformOffset)
    {
        if (AStaticMeshActor* MeshActor = Cast<AStaticMeshActor>(TargetActor)) MeshActor->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
        else if (USceneComponent* Root = TargetActor->GetRootComponent()) Root->SetMobility(EComponentMobility::Movable);
    }
    UE_LOG(LogTemp, Display, TEXT("AUDITOR_STATE_READY id=%s"), *TaskId);
}
bool AAuditorStateScenario::IsPlayerViewingTarget(APawn* Pawn, float& OutFacing, float& OutDistance) const
{
    if (!Pawn || !Pawn->Controller || !TargetActor) return false;
    FVector Origin; FRotator Rotation; Pawn->Controller->GetPlayerViewPoint(Origin, Rotation);
    FVector Center; FVector Extent; TargetActor->GetActorBounds(false, Center, Extent);
    const FVector Delta = Center - Origin;
    OutFacing = FVector::DotProduct(Rotation.Vector(), Delta.GetSafeNormal());
    OutDistance = FVector::Dist2D(Pawn->GetActorLocation(), Center);
    FHitResult Hit; FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorStateVisibility), true, Pawn);
    GetWorld()->LineTraceSingleByChannel(Hit, Origin, Center, ECC_Visibility, Params);
    return OutFacing >= FacingThreshold && (!Hit.bBlockingHit || Hit.GetActor() == TargetActor);
}
void AAuditorStateScenario::ApplyEffect()
{
    if (bApplied || !TargetActor) return;
    if (Effect == EAuditorScenarioEffect::Hide) { TargetActor->SetActorHiddenInGame(true); if (DisableCollisionWhenHidden) TargetActor->SetActorEnableCollision(false); }
    else if (Effect == EAuditorScenarioEffect::TransformOffset)
    {
        const FVector NewLocation = TargetActor->GetActorLocation() + LocationOffset;
        const FRotator NewRotation = TargetActor->GetActorRotation() + RotationOffset;
        TargetActor->SetActorLocationAndRotation(NewLocation, NewRotation, false, nullptr, ETeleportType::TeleportPhysics);
    }
    else if (Effect == EAuditorScenarioEffect::Material) { if (UMeshComponent* Mesh = TargetActor->FindComponentByClass<UMeshComponent>()) for (int32 Index = 0; Index < Mesh->GetNumMaterials(); ++Index) Mesh->SetMaterial(Index, ReplacementMaterial); }
    else if (Effect == EAuditorScenarioEffect::DisableCollision) TargetActor->SetActorEnableCollision(false);
    bApplied = true; UE_LOG(LogTemp, Display, TEXT("AUDITOR_STATE_APPLIED id=%s"), *TaskId);
}
void AAuditorStateScenario::RequestInteraction(AActor* RequestingPawn)
{
    if (Trigger != EAuditorScenarioTrigger::Interaction || bApplied || !TargetActor || !RequestingPawn) return;
    APawn* Pawn = Cast<APawn>(RequestingPawn); if (!Pawn) return;
    FVector Origin; FRotator Rotation;
    if (APlayerController* Controller = Cast<APlayerController>(Pawn->GetController())) Controller->GetPlayerViewPoint(Origin, Rotation); else return;
    FHitResult Hit; FCollisionQueryParams Params(SCENE_QUERY_STAT(AuditorStateInteraction), true, RequestingPawn);
    GetWorld()->LineTraceSingleByChannel(Hit, Origin, Origin + Rotation.Vector() * 250.0f, ECC_Visibility, Params);
    if (Hit.GetActor() == TargetActor) bInteractionRequested = true;
}
void AAuditorStateScenario::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (AuditorExploration::Pending(GetWorld())) return; if (bApplied || !TargetActor) return; SimulationAge += DeltaSeconds;
    APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0); float Facing = -1.0f; float Distance = TNumericLimits<float>::Max();
    const bool bViewing = IsPlayerViewingTarget(Pawn, Facing, Distance);
    if (Trigger == EAuditorScenarioTrigger::SimulationTime && SimulationAge >= DelaySeconds) ApplyEffect();
    else if (Trigger == EAuditorScenarioTrigger::LookAwayAfterSeen) { if (bViewing) bSeen = true; if (bSeen && Facing < 0.0f) ApplyEffect(); }
    else if (Trigger == EAuditorScenarioTrigger::LeaveAndReturn) { if (bViewing && Distance <= NearDistanceCm) bSeen = true; if (bSeen && Distance >= FarDistanceCm) bLeft = true; if (bLeft && Distance <= NearDistanceCm) ApplyEffect(); }
    else if (Trigger == EAuditorScenarioTrigger::PassByAfterSeen)
    {
        if (Pawn && !bPassReferenceInitialized)
        {
            FVector TargetCenter; FVector TargetExtent; TargetActor->GetActorBounds(false, TargetCenter, TargetExtent);
            const FVector InitialDelta = Pawn->GetActorLocation() - TargetCenter;
            bPassAlongX = FMath::Abs(InitialDelta.X) >= FMath::Abs(InitialDelta.Y);
            const float InitialCoordinate = bPassAlongX ? InitialDelta.X : InitialDelta.Y;
            InitialPassSide = InitialCoordinate < 0.0f ? -1.0f : 1.0f;
            PassReferenceCoordinate = bPassAlongX ? TargetCenter.X : TargetCenter.Y;
            bPassReferenceInitialized = true;
        }
        if (bViewing && Distance <= NearDistanceCm) { if (!bSeen) UE_LOG(LogTemp, Display, TEXT("AUDITOR_STATE_ARMED id=%s trigger=pass_by"), *TaskId); bSeen = true; }
        if (bSeen && bPassReferenceInitialized && Pawn)
        {
            const float PawnCoordinate = bPassAlongX ? Pawn->GetActorLocation().X : Pawn->GetActorLocation().Y;
            const float SignedDistanceFromStartSide = InitialPassSide * (PawnCoordinate - PassReferenceCoordinate);
            if (SignedDistanceFromStartSide <= -PassMarginCm) ApplyEffect();
        }
    }
    else if (Trigger == EAuditorScenarioTrigger::Interaction && bInteractionRequested) ApplyEffect();
}
