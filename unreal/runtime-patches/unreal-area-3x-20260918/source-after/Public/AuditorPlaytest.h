#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "AuditorPlaytest.generated.h"

UCLASS()
class AUDITORRUNTIME_API AAuditorRegion : public AActor
{
    GENERATED_BODY()
public:
    AAuditorRegion();
    virtual void BeginPlay() override;
    UPROPERTY(EditAnywhere, Category="Region") FVector BoundsMin = FVector(-1670, -1190, 139);
    UPROPERTY(EditAnywhere, Category="Region") FVector BoundsMax = FVector(-950, -330, 430);
    UPROPERTY(EditAnywhere, Category="Region") FString RegionName = TEXT("A / LIVING ROOM");
    UPROPERTY(EditAnywhere, Category="Region") FVector SpawnLocation = FVector(-1090, -660, 239);
    UPROPERTY(EditAnywhere, Category="Region") FRotator SpawnRotation = FRotator(0, 180, 0);
    UPROPERTY(EditAnywhere, Category="Validation") FVector BoundaryTestStart = FVector(-1095, -425, 239);
    UPROPERTY(EditAnywhere, Category="Validation") FVector BoundaryTestDirection = FVector(1, 0, 0);
    UPROPERTY(EditAnywhere, Category="Validation") TArray<FVector> TraversalPoints;
    UPROPERTY(EditAnywhere, Category="Region") TArray<FString> RegionMaps = {
        TEXT("/Game/Auditor/Regions/LivingRoom"),
        TEXT("/Game/Auditor/Regions/KitchenDining"),
        TEXT("/Game/Auditor/Regions/BedroomSuite")
    };
    // Optional task-local exclusions, used to keep exploration on its authored floor.
    TArray<FBox> ExplorationExclusions;
    float Clearance(const FVector& Position, float Radius) const;
};

UCLASS()
class AUDITORRUNTIME_API AAuditorCharacter : public ACharacter
{
    GENERATED_BODY()
public:
    AAuditorCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    UPROPERTY() TObjectPtr<AAuditorRegion> Region;
    UPROPERTY() TObjectPtr<class UCameraComponent> Camera;
    void ResetPosition();
    bool IsReviewPanelOpen() const { return bReviewPanelOpen; }
    const FString& ReviewNumber() const { return TaskNumber; }
    const FString& ReviewError() const { return TaskNumberError; }
private:
    void ToggleReviewPanel();
    void SetReviewPanel(bool bOpen);
    void TypeTaskDigit(int32 Digit);
    void ConfirmTaskNumber();
    void EraseTaskDigit();
    bool bManualReview = false;
    bool bReviewPanelOpen = false;
    bool bInitialReviewShown = false;
    FString TaskNumber;
    FString TaskNumberError;
    void Forward(float Value);
    void Sideways(float Value);
    void Turn(float Value);
    void Look(float Value);
    void Quit();
    void NextTask();
    void PreviousTask();
    void RestartTask();
    void Interact();
    void OpenLivingRoom();
    void OpenKitchenDining();
    void OpenBedroomSuite();
    void OpenRegion(int32 Index);
    void FinishTest(const TCHAR* TestName, bool bPassed);
    bool bBoundarySmokeTest = false;
    bool bTraversalTest = false;
    bool bInitialViewApplied = false;
    float TestElapsed = 0;
    FString VisualCheckPath;
    float VisualCheckElapsed = 0;
    bool bVisualCheckRequested = false;
    int32 TraversalIndex = 0;
    FVector TestStart;
    int32 PreviousBoundaryState = -1;
};

UCLASS()
class AUDITORRUNTIME_API AAuditorHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};

UCLASS()
class AUDITORRUNTIME_API AAuditorGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AAuditorGameMode();
};
