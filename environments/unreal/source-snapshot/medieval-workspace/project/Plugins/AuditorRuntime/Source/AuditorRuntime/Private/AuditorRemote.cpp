#include "AuditorRemote.h"
#include "AuditorPlaytest.h"
#include "AuditorTasks.h"
#include "Camera/CameraComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "ImageUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UnrealClient.h"

namespace {
constexpr double StepSeconds = 1.0 / 30.0;
TArray<TSharedPtr<FJsonValue>> Vec(const FVector& V)
{
    return {MakeShared<FJsonValueNumber>(V.X), MakeShared<FJsonValueNumber>(V.Y), MakeShared<FJsonValueNumber>(V.Z)};
}
}

void UAuditorRemote::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    Enabled = FParse::Param(FCommandLine::Get(), TEXT("AuditorServe"));
    if (!Enabled) return;
    if (!FParse::Value(FCommandLine::Get(), TEXT("AuditorIPC="), Directory) || FPaths::IsRelative(Directory))
    {
        UE_LOG(LogTemp, Error, TEXT("AUDITOR_REMOTE requires an absolute -AuditorIPC directory"));
        Enabled = false;
        return;
    }
    IFileManager::Get().MakeDirectory(*Directory, true);
    HadFixedTimeStep = FApp::UseFixedTimeStep();
    PreviousFixedDelta = FApp::GetFixedDeltaTime();
    FApp::SetFixedDeltaTime(StepSeconds);
    FApp::SetUseFixedTimeStep(true);
    ScreenshotHandle = UGameViewportClient::OnScreenshotCaptured().AddUObject(this, &UAuditorRemote::Screenshot);
}

void UAuditorRemote::Deinitialize()
{
    if (Enabled)
    {
        UGameViewportClient::OnScreenshotCaptured().Remove(ScreenshotHandle);
        FApp::SetUseFixedTimeStep(HadFixedTimeStep);
        FApp::SetFixedDeltaTime(PreviousFixedDelta);
    }
    Super::Deinitialize();
}

void UAuditorRemote::WriteJson(const FString& Name, const TSharedPtr<FJsonObject>& Object)
{
    FString Text;
    FJsonSerializer::Serialize(Object.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    const FString Path = Directory / Name;
    if (FFileHelper::SaveStringToFile(Text, *(Path + TEXT(".tmp")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
        IFileManager::Get().Move(*Path, *(Path + TEXT(".tmp")), true, true);
}

TSharedPtr<FJsonObject> UAuditorRemote::State() const
{
    auto R = MakeShared<FJsonObject>();
    auto* World = GetWorld();
    auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(World, 0));
    R->SetStringField(TEXT("request_id"), RequestId);
    R->SetStringField(TEXT("result"), Outcome);
    R->SetNumberField(TEXT("simulation_time"), World ? FMath::Max(0.0, double(World->GetTimeSeconds()) - StartTime) : 0);
    R->SetNumberField(TEXT("world_time"), World ? World->GetTimeSeconds() : 0);
    R->SetBoolField(TEXT("paused"), World && UGameplayStatics::IsGamePaused(World));
    R->SetNumberField(TEXT("actual_distance_cm"), Travelled);
    R->SetNumberField(TEXT("frame_number"), FrameNumber);
    R->SetStringField(TEXT("map"), World ? World->GetMapName() : TEXT(""));
    R->SetStringField(TEXT("task_id"), TEXT("baseline"));
    if (World) for (TActorIterator<AAuditorTasks> It(World); It; ++It)
    {
        R->SetStringField(TEXT("task_id"), It->ActiveId);
        break;
    }
    TArray<FString> ActorStates;
    if (World) for (TActorIterator<AActor> It(World); It; ++It)
        ActorStates.Add(It->GetName() + It->GetActorTransform().ToString() + FString::FromInt(It->IsHidden()) + FString::FromInt(It->GetActorEnableCollision()));
    ActorStates.Sort();
    R->SetStringField(TEXT("actor_state_digest"), FMD5::HashAnsiString(*FString::Join(ActorStates, TEXT("\n"))));
    if (Pawn)
    {
        R->SetArrayField(TEXT("position_cm"), Vec(Pawn->GetActorLocation()));
        R->SetArrayField(TEXT("camera_position_cm"), Vec(Pawn->Camera->GetComponentLocation()));
        const FRotator Rotation = Pawn->GetControlRotation();
        R->SetNumberField(TEXT("yaw_degree"), Rotation.Yaw);
        R->SetNumberField(TEXT("look_degree"), -FRotator::NormalizeAxis(Rotation.Pitch));
        R->SetNumberField(TEXT("boundary_clearance_cm"), Pawn->Region ? Pawn->Region->Clearance(Pawn->GetActorLocation(), 30) : 0);
    }
    return R;
}

void UAuditorRemote::Capture()
{
    Capturing = true;
    CaptureStarted = FPlatformTime::Seconds();
    FScreenshotRequest::RequestScreenshot(Directory / TEXT("capture.png"), false, false);
}

void UAuditorRemote::Screenshot(int32 Width, int32 Height, const TArray<FColor>& Pixels)
{
    if (!Capturing) return;
    TArray64<uint8> Compressed;
    FImageUtils::PNGCompressImageArray(Width, Height, TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()), Compressed);
    const FString Path = Directory / TEXT("observation.png");
    const bool Saved = FFileHelper::SaveArrayToFile(Compressed, *(Path + TEXT(".tmp"))) &&
        IFileManager::Get().Move(*Path, *(Path + TEXT(".tmp")), true, true);
    if (!Saved) Outcome = TEXT("capture_failed");
    ++FrameNumber;
    auto R = State();
    R->SetNumberField(TEXT("width"), Width);
    R->SetNumberField(TEXT("height"), Height);
    const FString FrameFile = FString::Printf(TEXT("frame_%08d.png"), FrameNumber);
    if (Saved && FFileHelper::SaveArrayToFile(Compressed, *(Directory / FrameFile)))
    {
        auto Sample = State();
        Sample->SetStringField(TEXT("file"), FrameFile);
        Frames.Add(MakeShared<FJsonValueObject>(Sample));
    }
    Capturing = false;
    if (ResumeAfterCapture && Saved)
    {
        ResumeAfterCapture = false;
        UGameplayStatics::SetGamePaused(GetWorld(), false);
        return;
    }
    R->SetArrayField(TEXT("frames"), Frames);
    WriteJson(TEXT("response.json"), R);
    LastRequestId = RequestId;
}

void UAuditorRemote::Finish(const FString& Result)
{
    Running = false;
    Settling = ResumeAfterCapture = false;
    Outcome = Result;
    if (auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(GetWorld(), 0)))
    {
        Pawn->ConsumeMovementInputVector();
        Pawn->GetCharacterMovement()->StopMovementImmediately();
        Pawn->GetCharacterMovement()->MaxWalkSpeed = 220;
    }
    UGameplayStatics::SetGamePaused(GetWorld(), true);
    Capture();
}

void UAuditorRemote::ReadCommand()
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *(Directory / TEXT("command.json")))) return;
    TSharedPtr<FJsonObject> Command;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Command) || !Command) return;
    FString Id;
    if (!Command->TryGetStringField(TEXT("request_id"), Id) || Id == LastRequestId) return;
    RequestId = Id;
    Travelled = 0;
    BlockedFrames = 0;
    ActionFrames = 0;
    Frames.Empty();
    Command->TryGetStringField(TEXT("action"), Action);
    auto* World = GetWorld();
    auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(World, 0));
    auto* Controller = UGameplayStatics::GetPlayerController(World, 0);
    if (!Pawn || !Controller) { Finish(TEXT("not_ready")); return; }
    if (Action == TEXT("reset"))
    {
        FString Map, Task;
        Command->TryGetStringField(TEXT("map"), Map);
        Command->TryGetStringField(TEXT("task"), Task);
        if (!Map.StartsWith(TEXT("/Game/Auditor/Regions/"))) { Finish(TEXT("invalid_map")); return; }
        LastRequestId = Id;
        Resetting = true;
        double Seed = 0;
        Command->TryGetNumberField(TEXT("seed"), Seed);
        FMath::RandInit(int32(Seed));
        UGameplayStatics::SetGamePaused(World, false);
        UGameplayStatics::OpenLevel(World, FName(*Map), true, TEXT("Task=") + Task);
        return;
    }
    if (Action == TEXT("snapshot"))
    {
        // State-only diagnostic: does not render, consume simulation ticks, or leak targets.
        Outcome = TEXT("ok");
        WriteJson(TEXT("response.json"), State());
        LastRequestId = Id;
        return;
    }
    double Value = 0;
    Outcome = TEXT("ok");
    Command->TryGetNumberField(TEXT("value"), Value);
    if (!FMath::IsFinite(Value)) { Finish(TEXT("invalid_value")); return; }
    if (Action == TEXT("move_up") || Action == TEXT("move_down"))
    {
        if (Value <= 0 || Value > 2000) { Finish(TEXT("invalid_distance")); return; }
        RequestedDistance = Value;
        FramesLeft = FMath::CeilToInt(Value / 220 / StepSeconds) + 60;
        PreviousLocation = Pawn->GetActorLocation();
    }
    else if (Action == TEXT("turn") || Action == TEXT("look"))
    {
        if (FMath::Abs(Value) > 360) { Finish(TEXT("invalid_angle")); return; }
        FramesLeft = FMath::Max(1, FMath::CeilToInt(FMath::Abs(Value) / 90 / StepSeconds));
        RotationPerFrame = Value / FramesLeft;
    }
    else if (Action == TEXT("idle"))
    {
        if (Value < StepSeconds || Value > 10) { Finish(TEXT("invalid_duration")); return; }
        FramesLeft = FMath::CeilToInt(Value / StepSeconds);
    }
    else if (Action == TEXT("interact"))
    {
        Outcome = TEXT("not_interactable");
        for (TActorIterator<AAuditorTasks> It(World); It; ++It) { Outcome = It->Interact(); break; }
        FramesLeft = 1;
    }
    else { Finish(TEXT("unknown_action")); return; }
    Running = true;
    UGameplayStatics::SetGamePaused(World, false);
}

void UAuditorRemote::Tick(float DeltaTime)
{
    UWorld* World = GetWorld();
    if (!World || !World->HasBegunPlay()) return;
    if (ActiveWorld.Get() != World)
    {
        ActiveWorld = World;
        Warmup = 60;
        Resetting = false;
        Capturing = Running = false;
        UGameplayStatics::SetGamePaused(World, false);
    }
    if (Resetting) return;
    auto* Pawn = Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(World, 0));
    auto* Controller = UGameplayStatics::GetPlayerController(World, 0);
    if (!Pawn || !Controller) return;
    if (Warmup > 0)
    {
        if (--Warmup == 0)
        {
            Pawn->DisableInput(Controller);
            StartTime = World->GetTimeSeconds();
            Finish(TEXT("ready"));
        }
        return;
    }
    if (Capturing)
    {
        if (FPlatformTime::Seconds() - CaptureStarted > 30)
        {
            Outcome = TEXT("capture_timeout");
            WriteJson(TEXT("response.json"), State());
            LastRequestId = RequestId;
            Capturing = false;
            Running = ResumeAfterCapture = Settling = false;
        }
        return;
    }
    if (!Running) { ReadCommand(); return; }
    if (Settling) { Finish(Outcome); return; }
    if (Action == TEXT("move_up") || Action == TEXT("move_down"))
    {
        const double Moved = FVector::Dist2D(PreviousLocation, Pawn->GetActorLocation());
        Travelled += Moved;
        PreviousLocation = Pawn->GetActorLocation();
        BlockedFrames = Moved < 0.01 ? BlockedFrames + 1 : 0;
        if (Travelled >= RequestedDistance - 0.1) { Finish(TEXT("ok")); return; }
        if (BlockedFrames >= 8) { Finish(TEXT("blocked")); return; }
        Pawn->GetCharacterMovement()->MaxWalkSpeed = FMath::Min(220.0, (RequestedDistance - Travelled) / StepSeconds);
        const FVector Direction = FRotator(0, Controller->GetControlRotation().Yaw, 0).Vector();
        Pawn->AddMovementInput(Direction, Action == TEXT("move_up") ? 1 : -1, true);
    }
    else if (Action == TEXT("turn") || Action == TEXT("look"))
    {
        auto Rotation = Controller->GetControlRotation();
        if (Action == TEXT("turn")) Rotation.Yaw += RotationPerFrame;
        else Rotation.Pitch = FMath::Clamp(FRotator::NormalizeAxis(Rotation.Pitch) - RotationPerFrame, -80.0, 80.0);
        Controller->SetControlRotation(Rotation);
    }
    if (--FramesLeft <= 0)
    {
        if (Action == TEXT("turn") || Action == TEXT("look")) Settling = true;
        else Finish(Travelled + 0.1 < RequestedDistance && Action.StartsWith(TEXT("move_")) ? TEXT("blocked") : Outcome);
        return;
    }
    if (++ActionFrames % 15 == 0)
    {
        ResumeAfterCapture = true;
        UGameplayStatics::SetGamePaused(World, true);
        Capture();
    }
}
