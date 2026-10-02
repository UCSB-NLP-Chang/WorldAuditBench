#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AuditorTasks.generated.h"

// The cooked maps carry the task catalog; no external manifest is needed to play.
UCLASS()
class AUDITORRUNTIME_API AAuditorTasks : public AActor
{
    GENERATED_BODY()
public:
    AAuditorTasks();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    UPROPERTY(EditAnywhere) FString CatalogJson;
    UPROPERTY(EditAnywhere) TObjectPtr<class UMaterialInterface> ErrorMaterial;
    void Cycle(int32 Direction);
    FString TaskIdAt(int32 Index) const;
    int32 TaskCount() const { return Tasks.Num(); }
    void Restart();
    FString Interact();
    FString InteractionPrompt() const;
    FString ActiveId = TEXT("baseline");
    void OpenTask(const FString& Id);
    bool IsTaskReady() const { return Initialized; }
private:
    TWeakObjectPtr<class AResidentialScenario> ResidentialScenario;
    bool Initialize();
    void UpdateEffect();
    void TestStep();
    void FinishTest(bool Passed, const FString& Detail);
    class AStaticMeshActor* FindMesh(const FString& Name) const;
    class AStaticMeshActor* Clone(class AStaticMeshActor* Source);
    FVector TargetCenter() const;
    void ApplyMaterial();
    UFUNCTION() void OnContact(UPrimitiveComponent* Component, AActor* Other, UPrimitiveComponent* OtherComponent, FVector Impulse, const FHitResult& Hit);
    void SetHose(const FString& Name, FVector Start, FVector End);
    UPROPERTY() TObjectPtr<class AStaticMeshActor> OperatingFan;
    float ContactAt = -1;
    float TestSample = 0;
    FVector TestPosition = FVector::ZeroVector;
    bool FanReversed = false;

    TArray<TSharedPtr<class FJsonValue>> Tasks;
    TSharedPtr<class FJsonObject> Spec;
    UPROPERTY() TObjectPtr<class AStaticMeshActor> Target;
    UPROPERTY() TObjectPtr<class AStaticMeshActor> Added;
    UPROPERTY() TObjectPtr<class UBoxComponent> Blocker;
    FTransform Original;
    FVector OriginalCenter = FVector::ZeroVector;
    FString Kind;
    bool Initialized = false;
    bool Seen = false;
    bool NearSeen = false;
    bool Left = false;
    bool Changed = false;
    bool Testing = false;
    int32 TestPhase = 0;
    float Age = 0;
    float PhaseAge = 0;
    float RemovedAt = -1;
    float ReviewCaptureAge = -1;
    bool TestFirstState = false;
    bool BaselineCollision = false;
};
