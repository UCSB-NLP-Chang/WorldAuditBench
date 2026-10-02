#include "AuditorPlaytest.h"
#include "AuditorExploration.h"
#include "AuditorTasks.h"
#include "AuditorStateScenario.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Widgets/SViewport.h"
#include "Input/Reply.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerInput.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Modules/ModuleManager.h"
#include "UnrealClient.h"
#include "HAL/FileManager.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, AuditorRuntime)

namespace
{

// Remote streams need Slate pointer routing for MouseX/MouseY, but must never
// request native high-precision input or lock the host cursor to the viewport.
class FAuditorRemoteInputMode final : public FInputModeDataBase
{
    virtual void ApplyInputMode(FReply& SlateOperations, UGameViewportClient& Viewport) const override
    {
        if (TSharedPtr<SViewport> Widget = Viewport.GetGameViewportWidget())
        {
            SlateOperations.SetUserFocus(Widget.ToSharedRef());
            SlateOperations.CaptureMouse(Widget.ToSharedRef());
            SlateOperations.ReleaseMouseLock();
        }
        Viewport.SetIgnoreInput(false);
        Viewport.SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
        Viewport.SetMouseLockMode(EMouseLockMode::DoNotLock);
        Viewport.SetHideCursorDuringCapture(false);
    }
};

void ApplyAuditorGameplayInputMode(APlayerController* PC)
{
    if (FParse::Param(FCommandLine::Get(), TEXT("AuditorRemoteInput")))
    {
        PC->SetInputMode(FAuditorRemoteInputMode());
        UE_LOG(LogTemp, Display, TEXT("AUDITOR_REMOTE_INPUT logical_capture=Slate host_high_precision=not_requested capture_mode=NoCapture lock_mode=DoNotLock"));
    }
    else
    {
        PC->SetInputMode(FInputModeGameOnly());
    }
}

const TCHAR* const GAuditorSceneMaps[] = {
    TEXT("/Game/Auditor/Urban/Cropped/Junction_Cropped"),
    TEXT("/Game/Auditor/Urban/Cropped/RearLane_Cropped"),
    TEXT("/Game/Auditor/Urban/Cropped/ServiceLane_Cropped"),
    TEXT("/Game/Auditor/Urban/Cropped/Shopfront_Cropped")
};
const TCHAR* const GAuditorSceneLabels[] = {
    TEXT("JUNCTION"),
    TEXT("REAR LANE"),
    TEXT("SERVICE LANE"),
    TEXT("SHOPFRONT")
};
bool GAuditorSceneChosen = false;
}

AAuditorRegion::AAuditorRegion()
{
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    Tags.Add(TEXT("task_boundary"));
}

void AAuditorRegion::BeginPlay()
{
    Super::BeginPlay();
    AuditorExploration::Expand(this);
    const FVector Mid = (BoundsMin + BoundsMax) * 0.5;
    const FVector Half = (BoundsMax - BoundsMin) * 0.5;
    // Invisible barriers block only the agent, leaving scenery and lighting intact.
    auto Barrier = [this](FVector Center, FVector Extent)
    {
        UBoxComponent* Box = NewObject<UBoxComponent>(this);
        AddInstanceComponent(Box);
        Box->SetupAttachment(RootComponent);
        Box->SetBoxExtent(Extent);
        Box->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        Box->SetCollisionObjectType(ECC_WorldStatic);
        Box->SetCollisionResponseToAllChannels(ECR_Ignore);
        Box->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
        Box->SetGenerateOverlapEvents(false);
        Box->SetCanEverAffectNavigation(false);
        Box->SetHiddenInGame(true);
        Box->ComponentTags.Add(TEXT("task_boundary"));
        Box->RegisterComponent();
        Box->SetWorldLocation(Center);
    };
    Barrier(FVector(BoundsMin.X - 10, Mid.Y, Mid.Z), FVector(10, Half.Y + 20, Half.Z + 100));
    Barrier(FVector(BoundsMax.X + 10, Mid.Y, Mid.Z), FVector(10, Half.Y + 20, Half.Z + 100));
    Barrier(FVector(Mid.X, BoundsMin.Y - 10, Mid.Z), FVector(Half.X + 20, 10, Half.Z + 100));
    Barrier(FVector(Mid.X, BoundsMax.Y + 10, Mid.Z), FVector(Half.X + 20, 10, Half.Z + 100));
    UE_LOG(LogTemp, Display, TEXT("AUDITOR_REGION_READY %s min=%s max=%s"), *RegionName, *BoundsMin.ToString(), *BoundsMax.ToString());
}

float AAuditorRegion::Clearance(const FVector& P, float Radius) const
{
    return FMath::Min(FMath::Min(P.X - BoundsMin.X, BoundsMax.X - P.X),
                      FMath::Min(P.Y - BoundsMin.Y, BoundsMax.Y - P.Y)) - Radius;
}

AAuditorCharacter::AAuditorCharacter()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->InitCapsuleSize(30, 90);
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("FirstPersonCamera"));
    Camera->SetupAttachment(GetCapsuleComponent());
    Camera->SetRelativeLocation(FVector(0, 0, 70));
    Camera->bUsePawnControlRotation = true;
    Camera->FieldOfView = 90;
    Camera->PostProcessSettings.bOverride_MotionBlurAmount = true;
    Camera->PostProcessSettings.MotionBlurAmount = 0;
    bUseControllerRotationYaw = true;
    GetCharacterMovement()->MaxWalkSpeed = 220;
    GetCharacterMovement()->MaxStepHeight = 25;
    GetCharacterMovement()->SetWalkableFloorAngle(45);
    GetCharacterMovement()->bOrientRotationToMovement = false;
    GetCharacterMovement()->NavAgentProps.bCanCrouch = false;
}

void AAuditorCharacter::BeginPlay()
{
    Super::BeginPlay();
    TActorIterator<AAuditorRegion> RegionIt(GetWorld());
    if (RegionIt) Region = *RegionIt;
    if (APlayerController* PC = Cast<APlayerController>(Controller))
    {
        ApplyAuditorGameplayInputMode(PC);
        PC->bShowMouseCursor = false;
        PC->PlayerCameraManager->ViewPitchMin = -80;
        PC->PlayerCameraManager->ViewPitchMax = 80;
    }
    ResetPosition();
    bBoundarySmokeTest = FParse::Param(FCommandLine::Get(), TEXT("AuditorBoundaryTest"));
    bTraversalTest = FParse::Param(FCommandLine::Get(), TEXT("AuditorTraversalTest"));
    bSceneLoadTest = FParse::Param(FCommandLine::Get(), TEXT("AuditorSceneLoadTest"));
    FParse::Value(FCommandLine::Get(), TEXT("AuditorVisualCheck="), VisualCheckPath);
    if (!VisualCheckPath.IsEmpty())
    {
        if (APlayerController* PC = Cast<APlayerController>(Controller))
        {
            PC->SetIgnoreMoveInput(true);
            PC->SetIgnoreLookInput(true);
        }
    }
    if (bBoundarySmokeTest && Region)
    {
        TestStart = Region->BoundaryTestStart;
        SetActorLocation(TestStart);
        if (Controller) Controller->SetControlRotation(Region->BoundaryTestDirection.Rotation());
    }
    const bool bAutomatedRun = bBoundarySmokeTest || bTraversalTest || bSceneLoadTest || !VisualCheckPath.IsEmpty();
    const bool bSkipSceneMenu = FParse::Param(FCommandLine::Get(), TEXT("AuditorSkipSceneMenu"));
    bSceneMenuVisible = !bAutomatedRun && !bSkipSceneMenu && !GAuditorSceneChosen;
    ApplySceneMenuInputState();
}

void AAuditorCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    static bool bMapped = false;
    if (!bMapped)
    {
        UPlayerInput::AddEngineDefinedAxisMapping(FInputAxisKeyMapping("AuditorForward", EKeys::W, 1));
        UPlayerInput::AddEngineDefinedAxisMapping(FInputAxisKeyMapping("AuditorForward", EKeys::S, -1));
        UPlayerInput::AddEngineDefinedAxisMapping(FInputAxisKeyMapping("AuditorSideways", EKeys::D, 1));
        UPlayerInput::AddEngineDefinedAxisMapping(FInputAxisKeyMapping("AuditorSideways", EKeys::A, -1));
        UPlayerInput::AddEngineDefinedAxisMapping(FInputAxisKeyMapping("AuditorTurn", EKeys::MouseX, 1));
        UPlayerInput::AddEngineDefinedAxisMapping(FInputAxisKeyMapping("AuditorLook", EKeys::MouseY, -1));
        bMapped = true;
    }
    Input->BindAxis("AuditorForward", this, &AAuditorCharacter::Forward);
    Input->BindAxis("AuditorSideways", this, &AAuditorCharacter::Sideways);
    Input->BindAxis("AuditorTurn", this, &AAuditorCharacter::Turn);
    Input->BindAxis("AuditorLook", this, &AAuditorCharacter::Look);
    Input->BindKey(EKeys::R, IE_Pressed, this, &AAuditorCharacter::RestartTask);
    Input->BindKey(EKeys::N, IE_Pressed, this, &AAuditorCharacter::NextTask);
    Input->BindKey(EKeys::P, IE_Pressed, this, &AAuditorCharacter::PreviousTask);
    Input->BindKey(EKeys::E, IE_Pressed, this, &AAuditorCharacter::Interact);
    Input->BindKey(EKeys::Escape, IE_Pressed, this, &AAuditorCharacter::Quit);
    Input->BindKey(EKeys::M, IE_Pressed, this, &AAuditorCharacter::ToggleSceneMenu);
    Input->BindKey(EKeys::F5, IE_Pressed, this, &AAuditorCharacter::RestartScene);
    Input->BindKey(EKeys::One, IE_Pressed, this, &AAuditorCharacter::OpenSceneOne);
    Input->BindKey(EKeys::Two, IE_Pressed, this, &AAuditorCharacter::OpenSceneTwo);
    Input->BindKey(EKeys::Three, IE_Pressed, this, &AAuditorCharacter::OpenSceneThree);
    Input->BindKey(EKeys::Four, IE_Pressed, this, &AAuditorCharacter::OpenSceneFour);
}

void AAuditorCharacter::Forward(float V) { AddMovementInput(GetActorForwardVector(), V); }
void AAuditorCharacter::Sideways(float V) { AddMovementInput(GetActorRightVector(), V); }
void AAuditorCharacter::Turn(float V) { AddControllerYawInput(V); }
void AAuditorCharacter::Look(float V) { AddControllerPitchInput(V); }
void AAuditorCharacter::Quit() { UKismetSystemLibrary::QuitGame(this, Cast<APlayerController>(Controller), EQuitPreference::Quit, false); }
void AAuditorCharacter::OpenRegion(int32 Index)
{
    // Review sessions are pinned to the task map selected by the supervisor.
    // Historical candidates may serialize old region lists: never follow them
    // while running in task-only mode, even if a numeric key arrives directly.
    if (FParse::Param(FCommandLine::Get(), TEXT("AuditorSkipSceneMenu")))
    {
        return;
    }
    // A packaged task may only navigate its own serialized region allowlist.
    // Never fall back to the historical clean-map table for missing entries.
    if (!IsValid(Region) || !Region->RegionMaps.IsValidIndex(Index))
    {
        return;
    }
    const FString& Map = Region->RegionMaps[Index];
    if (Map.IsEmpty() || !Map.StartsWith(TEXT("/Game/")))
    {
        return;
    }
    GAuditorSceneChosen = true;
    UGameplayStatics::OpenLevel(this, FName(*Map), true);
}
void AAuditorCharacter::OpenSceneOne() { OpenRegion(0); }
void AAuditorCharacter::OpenSceneTwo() { OpenRegion(1); }
void AAuditorCharacter::OpenSceneThree() { OpenRegion(2); }
void AAuditorCharacter::OpenSceneFour() { OpenRegion(3); }

void AAuditorCharacter::ApplySceneMenuInputState()
{
    if (APlayerController* PC = Cast<APlayerController>(Controller))
    {
        const bool bIgnoreGameplayInput = bSceneMenuVisible || !VisualCheckPath.IsEmpty();
        PC->SetIgnoreMoveInput(bIgnoreGameplayInput);
        PC->SetIgnoreLookInput(bIgnoreGameplayInput);
        PC->bShowMouseCursor = false;
    }
}

void AAuditorCharacter::ToggleSceneMenu()
{
    bSceneMenuVisible = !bSceneMenuVisible;
    ApplySceneMenuInputState();
}

void AAuditorCharacter::RestartScene()
{
    GAuditorSceneChosen = true;
    UGameplayStatics::OpenLevel(this, FName(*UGameplayStatics::GetCurrentLevelName(this, true)), true);
}

void AAuditorCharacter::NextTask() { TActorIterator<AAuditorTasks> It(GetWorld()); if (It) It->Cycle(1); }
void AAuditorCharacter::PreviousTask() { TActorIterator<AAuditorTasks> It(GetWorld()); if (It) It->Cycle(-1); }
void AAuditorCharacter::RestartTask() { TActorIterator<AAuditorTasks> It(GetWorld()); if (It) { It->Restart(); return; } ResetPosition(); }
void AAuditorCharacter::Interact()
{
    TActorIterator<AAuditorTasks> TasksIt(GetWorld());
    if (TasksIt) TasksIt->Interact();
    for (TActorIterator<AAuditorStateScenario> It(GetWorld()); It; ++It) It->RequestInteraction(this);
}

void AAuditorCharacter::FinishTest(const TCHAR* TestName, bool bPassed)
{
    UE_LOG(LogTemp, Display, TEXT("%s %s map=%s position=%s"), TestName, bPassed ? TEXT("PASS") : TEXT("FAIL"), *GetWorld()->GetMapName(), *GetActorLocation().ToString());
    bBoundarySmokeTest = false;
    bTraversalTest = false;
    GetCharacterMovement()->StopMovementImmediately();
    if (FParse::Param(FCommandLine::Get(), TEXT("AuditorTestExit")))
        FPlatformMisc::RequestExitWithStatus(false, bPassed ? 0 : 1);
}

void AAuditorCharacter::ResetPosition()
{
    if (!Region) return;
    GetCharacterMovement()->StopMovementImmediately();
    SetActorLocation(Region->SpawnLocation, false, nullptr, ETeleportType::TeleportPhysics);
    SetActorRotation(Region->SpawnRotation);
    if (Controller) Controller->SetControlRotation(Region->SpawnRotation);
}

void AAuditorCharacter::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (Controller && Region && !TActorIterator<AAuditorTasks>(GetWorld()) && GetWorld()->GetTimeSeconds() > 0.1f) AuditorExploration::Apply(this);
    if (!Region) return;
    if (bSceneLoadTest && TestElapsed > 1.0f)
    {
        FinishTest(TEXT("AUDITOR_SCENE_LOAD_TEST"), true);
        bSceneLoadTest = false;
        return;
    }
    if (!VisualCheckPath.IsEmpty())
    {
        VisualCheckElapsed += DeltaSeconds;
        if (VisualCheckElapsed > 5 && !bVisualCheckRequested)
        {
            // Slate capture is reliable on packaged Metal builds and includes the
            // runtime HUD, unlike direct render-target readback on some Macs.
            FScreenshotRequest::RequestScreenshot(VisualCheckPath, true, false);
            bVisualCheckRequested = true;
        }
        if (VisualCheckElapsed > 7 && IFileManager::Get().FileExists(*VisualCheckPath))
        {
            UE_LOG(LogTemp, Display, TEXT("AUDITOR_VISUAL_CHECK PASS %s"), *VisualCheckPath);
            VisualCheckPath.Empty();
            if (FParse::Param(FCommandLine::Get(), TEXT("AuditorTestExit"))) FPlatformMisc::RequestExit(false);
        }
        else if (VisualCheckElapsed > 20)
        {
            UE_LOG(LogTemp, Error, TEXT("AUDITOR_VISUAL_CHECK FAIL screenshot was not written"));
            VisualCheckPath.Empty();
            if (FParse::Param(FCommandLine::Get(), TEXT("AuditorTestExit"))) FPlatformMisc::RequestExitWithStatus(false, 1);
        }
    }
    // Possession can happen after BeginPlay; set the view once a controller exists.
    if (!bInitialViewApplied && Controller)
    {
        Controller->SetControlRotation(bBoundarySmokeTest ? Region->BoundaryTestDirection.Rotation() : Region->SpawnRotation);
        if (APlayerController* PC = Cast<APlayerController>(Controller))
        {
            ApplyAuditorGameplayInputMode(PC);
            PC->bShowMouseCursor = false;
            PC->PlayerCameraManager->ViewPitchMin = -80;
            PC->PlayerCameraManager->ViewPitchMax = 80;
            if (!VisualCheckPath.IsEmpty())
            {
                PC->SetIgnoreMoveInput(true);
                PC->SetIgnoreLookInput(true);
            }
        }
        ApplySceneMenuInputState();
        bInitialViewApplied = true;
    }
    const FVector P = GetActorLocation();
    const float Clearance = Region->Clearance(P, GetCapsuleComponent()->GetScaledCapsuleRadius());
    const int32 State = Clearance < 3 ? 2 : (Clearance < 150 ? 1 : 0);
    if (State != PreviousBoundaryState)
    {
        UE_LOG(LogTemp, Display, TEXT("AUDITOR_BOUNDARY state=%d clearance_cm=%.1f position=%s"), State, Clearance, *P.ToString());
        PreviousBoundaryState = State;
    }
    // Recovery only; ordinary containment is handled by swept capsule collision.
    if (Clearance < -5 || P.Z < Region->BoundsMin.Z - 100 || P.Z > Region->BoundsMax.Z + 100)
    {
        UE_LOG(LogTemp, Warning, TEXT("AUDITOR_OUT_OF_BOUNDS_RESET"));
        if (bBoundarySmokeTest || bTraversalTest) FinishTest(TEXT("AUDITOR_CONTAINMENT_TEST"), false);
        ResetPosition();
    }
    if (bBoundarySmokeTest)
    {
        TestElapsed += DeltaSeconds;
        if (TestElapsed < 5) AddMovementInput(Region->BoundaryTestDirection.GetSafeNormal2D(), 1);
        else
        {
            const bool bPassed = FVector::DotProduct(P - TestStart, Region->BoundaryTestDirection.GetSafeNormal2D()) > 50
                && FMath::Abs(Clearance) < 3 && FMath::Abs(P.Z - (TestStart.Z - 8)) < 20
                && GetCharacterMovement()->IsMovingOnGround();
            FinishTest(TEXT("AUDITOR_BOUNDARY_TEST"), bPassed);
        }
    }
    if (bTraversalTest)
    {
        TestElapsed += DeltaSeconds;
        if (Region->TraversalPoints.Num() < 2) { FinishTest(TEXT("AUDITOR_TRAVERSAL_TEST"), false); return; }
        const FVector Target = Region->TraversalPoints[TraversalIndex];
        const FVector Delta = Target - P;
        if (Delta.Size2D() < 15 && FMath::Abs(Delta.Z) < 20 && GetCharacterMovement()->IsMovingOnGround())
        {
            UE_LOG(LogTemp, Display, TEXT("AUDITOR_WAYPOINT %d/%d map=%s"), TraversalIndex + 1, Region->TraversalPoints.Num(), *GetWorld()->GetMapName());
            ++TraversalIndex;
            TestElapsed = 0;
            if (TraversalIndex == Region->TraversalPoints.Num()) FinishTest(TEXT("AUDITOR_TRAVERSAL_TEST"), true);
        }
        else if (TestElapsed > 8) FinishTest(TEXT("AUDITOR_TRAVERSAL_TEST"), false);
        else AddMovementInput(Delta.GetSafeNormal2D(), 1);
    }
    if (bSceneLoadTest) TestElapsed += DeltaSeconds;
}

void AAuditorHUD::DrawHUD()
{
    Super::DrawHUD();
    const AAuditorCharacter* Pawn = PlayerOwner ? Cast<AAuditorCharacter>(PlayerOwner->GetPawn()) : nullptr;
    if (!Canvas || !Pawn || !Pawn->Region) return;
    const AAuditorRegion* Region = Pawn->Region;
    const FVector P = Pawn->GetActorLocation();
    const float Distance = FMath::Max(0.f, Region->Clearance(P, Pawn->GetCapsuleComponent()->GetScaledCapsuleRadius()));
    const float W = Canvas->SizeX, H = Canvas->SizeY;
    const FLinearColor White(0.95, 0.97, 1), Amber(1, 0.72, 0.2), Dark(0.015, 0.025, 0.035, 0.85);
    DrawLine(W/2 - 4, H/2, W/2 + 4, H/2, White, 1);
    DrawLine(W/2, H/2 - 4, W/2, H/2 + 4, White, 1);
    // Fixed map orientation: the task perimeter is visible without altering scenery.
    const FVector Size = Region->BoundsMax - Region->BoundsMin;
    const float MapScale = FMath::Min(148.f / Size.X, 174.f / Size.Y);
    const float MW = Size.X * MapScale, MH = Size.Y * MapScale;
    const float MX = W - MW - 32, MY = 28;
    DrawRect(Dark, MX - 12, MY - 12, MW + 24, MH + 24);
    DrawLine(MX, MY, MX + MW, MY, Amber, 2);
    DrawLine(MX + MW, MY, MX + MW, MY + MH, Amber, 2);
    DrawLine(MX + MW, MY + MH, MX, MY + MH, Amber, 2);
    DrawLine(MX, MY + MH, MX, MY, Amber, 2);
    const float PX = MX + (P.X - Region->BoundsMin.X) / (Region->BoundsMax.X - Region->BoundsMin.X) * MW;
    const float PY = MY + (Region->BoundsMax.Y - P.Y) / (Region->BoundsMax.Y - Region->BoundsMin.Y) * MH;
    DrawRect(White, PX - 3, PY - 3, 6, 6);
    const FVector Forward = Pawn->GetActorForwardVector();
    DrawLine(PX, PY, PX + Forward.X * 14, PY - Forward.Y * 14, White, 2);
    if (Distance < 3)
    {
        DrawRect(Dark, W/2 - 252, H - 133, 504, 65);
        DrawText(TEXT("TASK BOUNDARY REACHED"), Amber, W/2 - 235, H - 124, nullptr, 1.4);
        DrawText(TEXT("Movement limited to this task area. This is not a scene bug."), White, W/2 - 235, H - 96, nullptr, 1.05);
    }
    if (Pawn->IsSceneMenuVisible())
    {
        const float PanelW = 440.f, PanelH = 300.f;
        const float X = (W - PanelW) * 0.5f, Y = (H - PanelH) * 0.5f;
        DrawRect(FLinearColor(0.01, 0.018, 0.028, 0.94), X, Y, PanelW, PanelH);
        DrawText(TEXT("CLEAN SCENE SELECT"), Amber, X + 34, Y + 26, nullptr, 1.55);
        DrawText(TEXT("Choose a baseline for inspection"), White, X + 34, Y + 58, nullptr, 1.0);
        for (int32 Index = 0; Index < UE_ARRAY_COUNT(GAuditorSceneLabels); ++Index)
        {
            const FString Row = FString::Printf(TEXT("[%d]  %s"), Index + 1, GAuditorSceneLabels[Index]);
            DrawText(Row, White, X + 48, Y + 100 + Index * 34, nullptr, 1.25);
        }
        DrawText(TEXT("M  close menu    F5  restart scene    ESC  quit"), White, X + 34, Y + 252, nullptr, 0.9);
    }
}

AAuditorGameMode::AAuditorGameMode()
{
    DefaultPawnClass = AAuditorCharacter::StaticClass();
    HUDClass = AAuditorHUD::StaticClass();
}
