#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AuditorCollisionProbe.generated.h"
// Opt-in cooked-runtime actual player-root capsule movement evidence, not walking QA.
UCLASS()
class AUDITORRUNTIME_API UAuditorCollisionProbe : public UTickableWorldSubsystem
{
 GENERATED_BODY()
public:
 virtual void OnWorldBeginPlay(UWorld& InWorld) override;
 virtual void Tick(float DeltaTime) override;
 virtual bool IsTickable() const override { return bActive; }
 virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAuditorCollisionProbe, STATGROUP_Tickables); }
private:
 void Finish(bool Passed, const FString& Reason);
 bool bActive=false, bAllPassed=true;
 float Age=0, Wait=0;
 int32 Index=0;
 FString Output;
 TSharedPtr<class FJsonObject> Spec;
 TArray<TSharedPtr<class FJsonValue>> Results;
};
