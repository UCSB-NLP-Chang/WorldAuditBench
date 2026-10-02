#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AuditorMigrationProbe.generated.h"
// Opt-in development evidence only; never activates without a private CLI route file.
UCLASS()
class AUDITORRUNTIME_API UAuditorMigrationProbe : public UTickableWorldSubsystem
{
 GENERATED_BODY()
public:
 virtual void OnWorldBeginPlay(UWorld& InWorld) override;
 virtual void Tick(float DeltaTime) override;
 virtual bool IsTickable() const override { return bActive; }
 virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAuditorMigrationProbe, STATGROUP_Tickables); }
private:
 void Finish(bool Success, const FString& Reason);
 bool SetStep();
 bool RecordStep();
 bool bActive=false, bPositioned=false, bRequested=false;
 float Age=0, StageAge=0;
 int32 Index=0;
 FString Output;
 TSharedPtr<class FJsonObject> Spec;
 TArray<TSharedPtr<class FJsonValue>> Trace;
 TWeakObjectPtr<class AAuditorStateScenario> Scenario;
 FVector InitialLocation;
 FRotator InitialRotation;
 bool InitialHidden=false, InitialCollision=true;
 FString InitialMaterial;
};
