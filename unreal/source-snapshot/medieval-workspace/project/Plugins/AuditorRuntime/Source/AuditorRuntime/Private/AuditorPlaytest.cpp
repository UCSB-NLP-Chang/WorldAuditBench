#include "AuditorPlaytest.h"
#include "AuditorTasks.h"
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

}

AAuditorRegion::AAuditorRegion()
{
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    Tags.Add(TEXT("task_boundary"));
}

void AAuditorRegion::BeginPlay()
{
    Super::BeginPlay();
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
    Camera->PostProcessSettings.bOverride_SceneFringeIntensity = true;
    Camera->PostProcessSettings.SceneFringeIntensity = 0;
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
    // Ancient residence stairs have authored risers up to 30.2 cm.
    if (GetWorld()->GetOutermost()->GetName().StartsWith(TEXT("/Game/Auditor/AncientCity/")))
        GetCharacterMovement()->MaxStepHeight = 35.f;
    // Engine development overlays are not part of the task observation.
    GAreScreenMessagesEnabled = false;
    for (TActorIterator<AAuditorRegion> It(GetWorld()); It; ++It) { Region = *It; break; }
    bManualReview = bool(TActorIterator<AAuditorTasks>(GetWorld())) &&
        !FParse::Param(FCommandLine::Get(), TEXT("AuditorRemoteInput")) &&
        !FParse::Param(FCommandLine::Get(), TEXT("AuditorServe")) &&
        !FParse::Param(FCommandLine::Get(), TEXT("AuditorTaskTest")) &&
        !FParse::Param(FCommandLine::Get(), TEXT("AuditorBoundaryTest")) &&
        !FParse::Param(FCommandLine::Get(), TEXT("AuditorTraversalTest")) &&
        !FParse::Param(FCommandLine::Get(), TEXT("AuditorReview")) &&
        !FParse::Value(FCommandLine::Get(), TEXT("AuditorVisualCheck="), VisualCheckPath);
    if (APlayerController* PC = Cast<APlayerController>(Controller))
    {
        ApplyAuditorGameplayInputMode(PC);
        PC->bShowMouseCursor = false;
        PC->PlayerCameraManager->ViewPitchMin = -80;
        PC->PlayerCameraManager->ViewPitchMax = 80;
    }
    ResetPosition();
    // The possessed pawn already has its initial view; task initialization may now aim it.
    bInitialViewApplied = Controller != nullptr;
    bBoundarySmokeTest = FParse::Param(FCommandLine::Get(), TEXT("AuditorBoundaryTest"));
    bTraversalTest = FParse::Param(FCommandLine::Get(), TEXT("AuditorTraversalTest"));
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
    Input->BindKey(EKeys::Escape, IE_Pressed, this, &AAuditorCharacter::ToggleReviewPanel).bExecuteWhenPaused = true;
    Input->BindKey(EKeys::Enter, IE_Pressed, this, &AAuditorCharacter::ConfirmTaskNumber).bExecuteWhenPaused = true;
    Input->BindKey(EKeys::BackSpace, IE_Pressed, this, &AAuditorCharacter::EraseTaskDigit).bExecuteWhenPaused = true;
    Input->BindKey(EKeys::F1, IE_Pressed, this, &AAuditorCharacter::OpenLivingRoom).bExecuteWhenPaused = true;
    Input->BindKey(EKeys::F2, IE_Pressed, this, &AAuditorCharacter::OpenKitchenDining).bExecuteWhenPaused = true;
    Input->BindKey(EKeys::F3, IE_Pressed, this, &AAuditorCharacter::OpenBedroomSuite).bExecuteWhenPaused = true;
    const FKey Digits[] = {EKeys::Zero, EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four,
        EKeys::Five, EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine};
    const FKey Numpad[] = {EKeys::NumPadZero, EKeys::NumPadOne, EKeys::NumPadTwo, EKeys::NumPadThree, EKeys::NumPadFour,
        EKeys::NumPadFive, EKeys::NumPadSix, EKeys::NumPadSeven, EKeys::NumPadEight, EKeys::NumPadNine};
    for (int32 Digit = 0; Digit < 10; ++Digit)
        for (const FKey& Key : {Digits[Digit], Numpad[Digit]})
        {
            FInputKeyBinding Binding(FInputChord(Key), IE_Pressed);
            Binding.bExecuteWhenPaused = true;
            Binding.KeyDelegate.GetDelegateForManualSet().BindLambda([this, Digit]() { TypeTaskDigit(Digit); });
            Input->KeyBindings.Add(MoveTemp(Binding));
        }
}

void AAuditorCharacter::Forward(float V) { if (!bReviewPanelOpen) AddMovementInput(GetActorForwardVector(), V); }
void AAuditorCharacter::Sideways(float V) { if (!bReviewPanelOpen) AddMovementInput(GetActorRightVector(), V); }
void AAuditorCharacter::Turn(float V) { if (!bReviewPanelOpen) AddControllerYawInput(V); }
void AAuditorCharacter::Look(float V) { if (!bReviewPanelOpen) AddControllerPitchInput(V); }

void AAuditorCharacter::SetReviewPanel(bool bOpen)
{
    if (!bManualReview) return;
    bReviewPanelOpen = bOpen;
    GetCharacterMovement()->StopMovementImmediately();
    ConsumeMovementInputVector();
    if (auto* PC = Cast<APlayerController>(Controller))
    {
        if (bOpen)
        {
            FInputModeGameAndUI Mode;
            Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
            Mode.SetHideCursorDuringCapture(false);
            PC->SetInputMode(Mode);
        }
        else ApplyAuditorGameplayInputMode(PC);
        PC->bShowMouseCursor = bOpen;
    }
    if (auto* Viewport = GetWorld()->GetGameViewport())
    {
        Viewport->SetMouseCaptureMode((bOpen || FParse::Param(FCommandLine::Get(), TEXT("AuditorRemoteInput"))) ? EMouseCaptureMode::NoCapture : EMouseCaptureMode::CapturePermanently_IncludingInitialMouseDown);
        Viewport->SetMouseLockMode((bOpen || FParse::Param(FCommandLine::Get(), TEXT("AuditorRemoteInput"))) ? EMouseLockMode::DoNotLock : EMouseLockMode::LockOnCapture);
    }
    UGameplayStatics::SetGamePaused(this, bOpen);
    UE_LOG(LogTemp, Display, TEXT("AUDITOR_MANUAL_REVIEW open=%d paused=%d cursor=%d"), bOpen,
        UGameplayStatics::IsGamePaused(this), Cast<APlayerController>(Controller) ? Cast<APlayerController>(Controller)->bShowMouseCursor : 0);
}

void AAuditorCharacter::ToggleReviewPanel()
{
    if (FParse::Param(FCommandLine::Get(), TEXT("AuditorRemoteInput"))) return; // Browser Esc releases pointer lock.
    if (!bManualReview) { Quit(); return; }
    TaskNumber.Empty();
    TaskNumberError.Empty();
    SetReviewPanel(!bReviewPanelOpen);
}

void AAuditorCharacter::TypeTaskDigit(int32 Digit)
{
    if (!bManualReview)
    {
        if (!FParse::Param(FCommandLine::Get(), TEXT("AuditorServe")) && Digit >= 1 && Digit <= 3) OpenRegion(Digit - 1);
        return;
    }
    if (!bReviewPanelOpen) { TaskNumber.Empty(); SetReviewPanel(true); }
    TaskNumberError.Empty();
    if (TaskNumber.Len() < 2) TaskNumber.AppendInt(Digit);
}

void AAuditorCharacter::EraseTaskDigit()
{
    if (bReviewPanelOpen && !TaskNumber.IsEmpty()) TaskNumber.LeftChopInline(1);
    TaskNumberError.Empty();
}

void AAuditorCharacter::ConfirmTaskNumber()
{
    if (!bManualReview || !bReviewPanelOpen) return;
    if (TaskNumber.IsEmpty()) { SetReviewPanel(false); return; }
    const int32 Number = FCString::Atoi(*TaskNumber);
    for (TActorIterator<AAuditorTasks> It(GetWorld()); It; ++It)
    {
        if (!It->IsTaskReady()) { TaskNumberError = TEXT("The scene is still loading."); return; }
        if (Number < 1 || Number > It->TaskCount()) { TaskNumberError = FString::Printf(TEXT("Choose a task from 1 to %d."), It->TaskCount()); return; }
        const FString Id = It->TaskIdAt(Number - 1);
        if (Id.IsEmpty()) { TaskNumberError = TEXT("Task unavailable."); return; }
        UE_LOG(LogTemp, Display, TEXT("AUDITOR_MANUAL_SELECT %s"), *Id);
        SetReviewPanel(false);
        It->OpenTask(Id);
        return;
    }
}

void AAuditorCharacter::Quit() { UKismetSystemLibrary::QuitGame(this, Cast<APlayerController>(Controller), EQuitPreference::Quit, false); }
void AAuditorCharacter::OpenRegion(int32 Index)
{
    if (Region && Region->RegionMaps.IsValidIndex(Index))
    {
        if (bReviewPanelOpen) SetReviewPanel(false);
        UGameplayStatics::OpenLevel(this, FName(*Region->RegionMaps[Index]), true, TEXT("Task=baseline"));
    }
}
void AAuditorCharacter::OpenLivingRoom() { OpenRegion(0); }
void AAuditorCharacter::OpenKitchenDining() { OpenRegion(1); }
void AAuditorCharacter::OpenBedroomSuite() { OpenRegion(2); }

void AAuditorCharacter::NextTask() { for (TActorIterator<AAuditorTasks> It(GetWorld()); It; ++It) { It->Cycle(1); break; } }
void AAuditorCharacter::PreviousTask() { for (TActorIterator<AAuditorTasks> It(GetWorld()); It; ++It) { It->Cycle(-1); break; } }
void AAuditorCharacter::RestartTask() { for (TActorIterator<AAuditorTasks> It(GetWorld()); It; ++It) { It->Restart(); return; } ResetPosition(); }
void AAuditorCharacter::Interact() { for (TActorIterator<AAuditorTasks> It(GetWorld()); It; ++It) { It->Interact(); break; } }

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
    if (!Region) return;
    if (!VisualCheckPath.IsEmpty())
    {
        VisualCheckElapsed += DeltaSeconds;
        if (VisualCheckElapsed > 5 && !bVisualCheckRequested)
        {
            FScreenshotRequest::RequestScreenshot(VisualCheckPath, true, false);
            VisualCheckElapsed = 0;
            bVisualCheckRequested = true;
        }
        if (bVisualCheckRequested && IFileManager::Get().FileExists(*VisualCheckPath))
        {
            UE_LOG(LogTemp, Display, TEXT("AUDITOR_VISUAL_CHECK PASS %s"), *VisualCheckPath);
            VisualCheckPath.Empty();
            if (FParse::Param(FCommandLine::Get(), TEXT("AuditorTestExit"))) FPlatformMisc::RequestExit(false);
        }
        else if (bVisualCheckRequested && VisualCheckElapsed > 60)
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
        bInitialViewApplied = true;
    }
    if (bManualReview && !bInitialReviewShown && Controller)
        for (TActorIterator<AAuditorTasks> It(GetWorld()); It; ++It)
            if (It->IsTaskReady())
            {
                bInitialReviewShown = true;
                SetReviewPanel(true);
                break;
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
    if (Pawn->IsReviewPanelOpen())
    {
        FString Active = TEXT("BASELINE");
        int32 Count = 0;
        for (TActorIterator<AAuditorTasks> It(GetWorld()); It; ++It) { Active = It->ActiveId; Count = It->TaskCount(); break; }
        DrawRect(Dark, W/2 - 240, H/2 - 110, 480, 220);
        DrawText(TEXT("PAUSED  /  ") + Active, White, W/2 - 215, H/2 - 88, nullptr, 1.5);
        DrawText(FString::Printf(TEXT("Task 1-%d:  "), Count) + Pawn->ReviewNumber() + TEXT("_"), White, W/2 - 215, H/2 - 43, nullptr, 1.5);
        DrawText(TEXT("Enter: load task / continue     Esc: continue"), White, W/2 - 215, H/2 + 6, nullptr, 1.0);
        DrawText(TEXT("F1 / F2 / F3: baseline regions"), White, W/2 - 215, H/2 + 32, nullptr, 1.0);
        if (!Pawn->ReviewError().IsEmpty()) DrawText(Pawn->ReviewError(), Amber, W/2 - 215, H/2 + 64, nullptr, 1.0);
        return;
    }
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
}

AAuditorGameMode::AAuditorGameMode()
{
    DefaultPawnClass = AAuditorCharacter::StaticClass();
    HUDClass = AAuditorHUD::StaticClass();
}
