#include "AuditorReviewSwitch.h"
#include "AuditorTasks.h"
#include "AuditorPlaytest.h"
#include "Engine/StaticMeshActor.h"
#include "Components/StaticMeshComponent.h"
#include "Camera/CameraComponent.h"
#include "Materials/MaterialInterface.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Pawn.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UnrealClient.h"

void UAuditorReviewSwitch::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    if (!FParse::Value(FCommandLine::Get(), TEXT("AuditorReviewIPC="), Directory) || FPaths::IsRelative(Directory)) { Directory.Empty(); return; }
    IFileManager::Get().MakeDirectory(*Directory, true);
}

void UAuditorReviewSwitch::Respond(const FString& Status)
{
    UWorld* World = GetWorld();
    auto R = MakeShared<FJsonObject>();
    R->SetStringField(TEXT("request_id"), RequestId);
    R->SetStringField(TEXT("status"), Status);
    R->SetNumberField(TEXT("pid"), FPlatformProcess::GetCurrentProcessId());
    R->SetNumberField(TEXT("generation"), Generation);
    R->SetStringField(TEXT("map"), World ? World->GetOutermost()->GetName() : TEXT(""));
    for (TActorIterator<AAuditorTasks> It(World); It; ++It) { R->SetStringField(TEXT("task"), It->ActiveId); break; }
    if (APawn* Pawn = UGameplayStatics::GetPlayerPawn(World, 0))
    {
        const FVector P = Pawn->GetActorLocation();
        R->SetArrayField(TEXT("position"), {MakeShared<FJsonValueNumber>(P.X), MakeShared<FJsonValueNumber>(P.Y), MakeShared<FJsonValueNumber>(P.Z)});
    }
    // Optional local-only QA state. Never returned by the public review API.
    if (FParse::Param(FCommandLine::Get(), TEXT("AuditorReviewDiagnostics")))
    {
        TArray<TSharedPtr<FJsonValue>> Actors;
        for (TActorIterator<AActor> It(World); It; ++It)
        {
            FString Tag;
            for (const FName& T : It->Tags) if (T.ToString().StartsWith(TEXT("auditor_actor:"))) { Tag = T.ToString(); break; }
            if (Tag.IsEmpty()) continue;
            auto A = MakeShared<FJsonObject>(); A->SetStringField(TEXT("tag"), Tag);
            A->SetStringField(TEXT("transform"), It->GetActorTransform().ToString());
            if (auto* MeshActor = Cast<AStaticMeshActor>(*It)) {
                A->SetBoolField(TEXT("simulating"),MeshActor->GetStaticMeshComponent()->IsSimulatingPhysics());
                TArray<TSharedPtr<FJsonValue>> Materials;
                for (int32 I=0; I<MeshActor->GetStaticMeshComponent()->GetNumMaterials(); ++I)
                    Materials.Add(MakeShared<FJsonValueString>(GetPathNameSafe(MeshActor->GetStaticMeshComponent()->GetMaterial(I))));
                A->SetArrayField(TEXT("materials"),Materials);
            }
            A->SetBoolField(TEXT("hidden"), It->IsHidden()); A->SetBoolField(TEXT("collision"), It->GetActorEnableCollision());
            Actors.Add(MakeShared<FJsonValueObject>(A));
        }
        R->SetArrayField(TEXT("actors"), Actors);
    }
    FString Text; FJsonSerializer::Serialize(R, TJsonWriterFactory<>::Create(&Text));
    const FString Path = Directory / TEXT("response.json");
    if (FFileHelper::SaveStringToFile(Text, *(Path + TEXT(".tmp")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM)) IFileManager::Get().Move(*Path, *(Path + TEXT(".tmp")), true, true);
}

void UAuditorReviewSwitch::Tick(float DeltaTime)
{
    UWorld* World = GetWorld();
    if (!World || !World->HasBegunPlay()) return;
    if (ObservedWorld.Get() != World) { ObservedWorld = World; ++Generation; StableFor = 0; }
    AAuditorTasks* TaskActor = nullptr;
    for (TActorIterator<AAuditorTasks> It(World); It; ++It) { TaskActor = *It; break; }
    if (!TaskActor || !TaskActor->IsTaskReady() || !UGameplayStatics::GetPlayerPawn(World, 0)) return;
    if (Pending)
    {
        if (Generation <= RequestedGeneration) return;
        if (!ExpectedMap.IsEmpty() && (World->GetOutermost()->GetName() != ExpectedMap || TaskActor->ActiveId != ExpectedTask)) return;
        StableFor += DeltaTime;
        if (StableFor < 0.5f) return;
        Pending = false;
        Respond(TEXT("ready"));
    }
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *(Directory / TEXT("command.json")))) return;
    TSharedPtr<FJsonObject> C;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), C) || !C) return;
    FString Id, Action, Map, Task;
    if (!C->TryGetStringField(TEXT("request_id"), Id) || Id.IsEmpty() || Id == RequestId) return;
    RequestId = Id;
    C->TryGetStringField(TEXT("action"), Action);
    if (Action == TEXT("view") && FParse::Param(FCommandLine::Get(), TEXT("AuditorReviewDiagnostics")))
    {
        const TArray<TSharedPtr<FJsonValue>> *Position, *Aim;
        auto* Pawn=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(World,0));
        if (!Pawn || !Pawn->Controller || !C->TryGetArrayField(TEXT("position"),Position) || Position->Num()!=3 || !C->TryGetArrayField(TEXT("aim"),Aim) || Aim->Num()!=3) { Respond(TEXT("invalid_view")); return; }
        FVector P((*Position)[0]->AsNumber(),(*Position)[1]->AsNumber(),(*Position)[2]->AsNumber());
        FVector A((*Aim)[0]->AsNumber(),(*Aim)[1]->AsNumber(),(*Aim)[2]->AsNumber());
        if (P.ContainsNaN() || A.ContainsNaN()) { Respond(TEXT("invalid_view")); return; }
        Pawn->SetActorLocation(P);
        Pawn->Controller->SetControlRotation((A-Pawn->Camera->GetComponentLocation()).Rotation());
        Respond(TEXT("ready"));return;
    }
    if (Action == TEXT("snapshot")) { Respond(TEXT("ready")); return; }
    if (Action == TEXT("capture") && FParse::Param(FCommandLine::Get(), TEXT("AuditorReviewDiagnostics")))
    { FScreenshotRequest::RequestScreenshot(Directory / (Id + TEXT(".png")), false, false); Respond(TEXT("ready")); return; }
    C->TryGetStringField(TEXT("map"), Map); C->TryGetStringField(TEXT("task"), Task);
    const bool Subway = FString(FApp::GetProjectName()) == TEXT("Subway");
    const bool Industrial = FString(FApp::GetProjectName()) == TEXT("FactoryEnvironmentCollect");
    const TArray<FString> Maps = Industrial ? TArray<FString>{TEXT("/Game/Auditor/Industrial/AssemblyHall"), TEXT("/Game/Auditor/Industrial/VehicleTest"), TEXT("/Game/Auditor/Industrial/ControlRoom")} : Subway ? TArray<FString>{TEXT("/Game/Auditor/Subway/Concourse"), TEXT("/Game/Auditor/Subway/Platform"), TEXT("/Game/Auditor/Subway/Trackside")} : TArray<FString>{TEXT("/Game/Auditor/Regions/LivingRoom"), TEXT("/Game/Auditor/Regions/KitchenDining"), TEXT("/Game/Auditor/Regions/BedroomSuite")};
    bool ValidTask = Task == TEXT("baseline");
    for (int32 I = 0; I < TaskActor->TaskCount(); ++I) if (TaskActor->TaskIdAt(I) == Task) ValidTask = true;
    if (Action != TEXT("switch") || !Maps.Contains(Map) || !ValidTask) { Respond(TEXT("invalid_target")); return; }
    ExpectedMap = Map; ExpectedTask = Task; RequestedGeneration = Generation; Pending = true; StableFor = 0;
    Respond(TEXT("switching"));
    if (auto* PC = UGameplayStatics::GetPlayerController(World, 0)) PC->FlushPressedKeys();
    UGameplayStatics::SetGamePaused(World, false);
    // Reload the authored world to reset actors, transient effects, physics,
    // timers and player position. GameInstance and Pixel Streaming remain alive.
    UGameplayStatics::OpenLevel(World, FName(*Map), true, TEXT("Task=") + Task);
}
