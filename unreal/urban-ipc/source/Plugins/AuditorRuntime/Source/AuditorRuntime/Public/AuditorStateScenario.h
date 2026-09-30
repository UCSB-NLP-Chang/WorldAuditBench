#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AuditorStateScenario.generated.h"

UENUM(BlueprintType)
enum class EAuditorScenarioTrigger : uint8
{
    SimulationTime,
    LookAwayAfterSeen,
    LeaveAndReturn,
    PassByAfterSeen,
    Interaction
};

UENUM(BlueprintType)
enum class EAuditorScenarioEffect : uint8
{
    Hide,
    TransformOffset,
    Material,
    DisableCollision
};

UCLASS()
class AUDITORRUNTIME_API AAuditorStateScenario : public AActor
{
    GENERATED_BODY()
public:
    AAuditorStateScenario();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    UPROPERTY(EditAnywhere, Category="Scenario") FString TaskId;
    UPROPERTY(EditAnywhere, Category="Scenario") TObjectPtr<AActor> TargetActor;
    UPROPERTY(EditAnywhere, Category="Scenario") EAuditorScenarioTrigger Trigger = EAuditorScenarioTrigger::SimulationTime;
    UPROPERTY(EditAnywhere, Category="Scenario") EAuditorScenarioEffect Effect = EAuditorScenarioEffect::Hide;
    UPROPERTY(EditAnywhere, Category="Scenario", meta=(ClampMin="0.0")) float DelaySeconds = 2.0f;
    UPROPERTY(EditAnywhere, Category="Scenario", meta=(ClampMin="0.0")) float NearDistanceCm = 450.0f;
    UPROPERTY(EditAnywhere, Category="Scenario", meta=(ClampMin="0.0")) float FarDistanceCm = 900.0f;
    UPROPERTY(EditAnywhere, Category="Scenario", meta=(ClampMin="0.0")) float PassMarginCm = 120.0f;
    UPROPERTY(EditAnywhere, Category="Scenario", meta=(ClampMin="-1.0", ClampMax="1.0")) float FacingThreshold = 0.75f;
    UPROPERTY(EditAnywhere, Category="Scenario") FVector LocationOffset = FVector::ZeroVector;
    UPROPERTY(EditAnywhere, Category="Scenario") FRotator RotationOffset = FRotator::ZeroRotator;
    UPROPERTY(EditAnywhere, Category="Scenario") TObjectPtr<class UMaterialInterface> ReplacementMaterial;
    UPROPERTY(EditAnywhere, Category="Scenario") bool DisableCollisionWhenHidden = true;
    void RequestInteraction(AActor* RequestingPawn);
private:
    bool IsPlayerViewingTarget(class APawn* Pawn, float& OutFacing, float& OutDistance) const;
    void ApplyEffect();
    bool bSeen = false;
    bool bLeft = false;
    bool bInteractionRequested = false;
    bool bApplied = false;
    bool bPassReferenceInitialized = false;
    bool bPassAlongX = false;
    float InitialPassSide = 1.0f;
    float PassReferenceCoordinate = 0.0f;
    float SimulationAge = 0.0f;
};
