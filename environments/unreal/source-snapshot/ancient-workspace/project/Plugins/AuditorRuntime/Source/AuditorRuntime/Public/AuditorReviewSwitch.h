#pragma once
#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "AuditorReviewSwitch.generated.h"

// Private filesystem IPC owned by the authenticated review supervisor. Does not
// change timing or disable player input, unlike the offline AuditorServe API.
UCLASS()
class AUDITORRUNTIME_API UAuditorReviewSwitch : public UGameInstanceSubsystem, public FTickableGameObject
{
    GENERATED_BODY()
public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Tick(float DeltaTime) override;
    virtual bool IsTickable() const override { return !Directory.IsEmpty() && !IsTemplate(); }
    virtual bool IsTickableWhenPaused() const override { return true; }
    virtual UWorld* GetTickableGameObjectWorld() const override { return GetWorld(); }
    virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(AuditorReviewSwitch, STATGROUP_Tickables); }
private:
    void Respond(const FString& Status);
    FString Directory, RequestId, ExpectedMap, ExpectedTask;
    TWeakObjectPtr<UWorld> ObservedWorld;
    int32 Generation = 0;
    int32 RequestedGeneration = 0;
    bool Pending = true;
    float StableFor = 0;
};
