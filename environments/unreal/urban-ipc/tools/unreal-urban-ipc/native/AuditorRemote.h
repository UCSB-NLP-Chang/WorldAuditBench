#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "AuditorRemote.generated.h"

// Local IPC only. The HTTP environment service owns authentication, serialization
// and request deduplication. Disabled unless launched with -AuditorServe.
UCLASS()
class AUDITORRUNTIME_API UAuditorRemote : public UGameInstanceSubsystem, public FTickableGameObject
{
    GENERATED_BODY()
public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
    virtual void Tick(float DeltaTime) override;
    virtual bool IsTickable() const override { return Enabled && !IsTemplate(); }
    virtual bool IsTickableWhenPaused() const override { return true; }
    virtual UWorld* GetTickableGameObjectWorld() const override { return GetWorld(); }
    virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(AuditorRemote, STATGROUP_Tickables); }
private:
    void ReadCommand();
    void Finish(const FString& Result);
    void Capture();
    void Screenshot(int32 Width, int32 Height, const TArray<FColor>& Pixels);
    void WriteJson(const FString& Name, const TSharedPtr<class FJsonObject>& Object);
    TSharedPtr<class FJsonObject> State() const;
    bool Enabled = false;
    bool Capturing = false;
    bool Running = false;
    bool Resetting = false;
    bool Settling = false;
    bool ResumeAfterCapture = false;
    bool HadFixedTimeStep = false;
    double PreviousFixedDelta = 0;
    int32 Warmup = 60;
    int32 FramesLeft = 0;
    int32 FrameNumber = 0;
    int32 BlockedFrames = 0;
    int32 ActionFrames = 0;
    double StartTime = 0;
    double CaptureStarted = 0;
    double RequestedDistance = 0;
    double Travelled = 0;
    double RotationPerFrame = 0;
    FString Directory;
    FString AssignedTask;
    FString RequestId;
    FString LastRequestId;
    FString Action;
    FString Outcome;
    FVector PreviousLocation = FVector::ZeroVector;
    TWeakObjectPtr<UWorld> ActiveWorld;
    FDelegateHandle ScreenshotHandle;
    TArray<TSharedPtr<class FJsonValue>> Frames;
};
