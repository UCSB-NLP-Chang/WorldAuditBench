#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ResidentialScenario.generated.h"

// Spawned at runtime: no properties added to the legacy cooked map actors.
UCLASS()
class AUDITORRUNTIME_API AResidentialScenario : public AActor
{
    GENERATED_BODY()
public:
    AResidentialScenario();
    bool Configure(class AAuditorTasks* Catalog, TSharedPtr<class FJsonObject> Definition);
    virtual void Tick(float DeltaSeconds) override;
    FString Interact();
private:
    class AStaticMeshActor* Find(const FString& Name) const;
    class AStaticMeshActor* Copy(class AStaticMeshActor* Source);
    class AStaticMeshActor* Shape(const TCHAR* Asset, FVector Center, FVector Scale, class UMaterialInterface* Material);
    void Pipe(FVector A, FVector B);
    void Label(FVector Position, const FString& Text);
    void SetView(FVector Position, FVector Aim);
    bool InView(class AStaticMeshActor* Object) const;
    bool DoorBlocked(float Angle) const;
    void SetupCommon();
    void StepVerification(float DeltaSeconds);
    void Finish(bool Pass, const FString& Detail);
    UFUNCTION() void CupContact(UPrimitiveComponent* Component, AActor* Other, UPrimitiveComponent* OtherComponent, FVector Impulse, const FHitResult& Hit);
    TSharedPtr<class FJsonObject> Spec;
    TWeakObjectPtr<class AAuditorTasks> Catalog;
    UPROPERTY() TObjectPtr<class AStaticMeshActor> Target;
    UPROPERTY() TObjectPtr<class AStaticMeshActor> Extra;
    UPROPERTY() TObjectPtr<class AStaticMeshActor> Cup;
    UPROPERTY() TObjectPtr<class UBoxComponent> CupBody;
    UPROPERTY() TObjectPtr<class UBoxComponent> Barrier;
    UPROPERTY() TObjectPtr<class AStaticMeshActor> Door;
    UPROPERTY() TObjectPtr<class AStaticMeshActor> Stool;
    UPROPERTY() TObjectPtr<class AStaticMeshActor> Fan;
    UPROPERTY() TObjectPtr<class UMaterialInterface> CupMaterial;
    FTransform Original, DoorOriginal, CupOriginal, FanOriginal;
    FVector Center, Probe, FarProbe, CupCenter;
    FString Id, Kind;
    bool Inject = false, Test = false, Review = false, Ready = false;
    bool Seen = false, Left = false, Changed = false, Released = false;
    bool DoorRequested = false, Verified = true, Capturing = false;
    float Age = 0, PhaseTime = 0, ContactAge = -1, ReleaseAge = -1;
    float DoorAngle = 0, FanAngle = 0, LastSample = 0;
    int32 Phase = 0, Contacts = 0, Excitations = 0;
    FVector SamplePosition;
};
