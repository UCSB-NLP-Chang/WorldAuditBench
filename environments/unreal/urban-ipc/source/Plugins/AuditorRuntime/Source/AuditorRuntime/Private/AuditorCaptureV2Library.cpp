#include "AuditorCaptureV2Library.h"

#include "CoreGlobals.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "SceneInterface.h"

#if WITH_EDITOR
#include "AssetCompilingManager.h"
#include "Components/ReflectionCaptureComponent.h"
#include "Components/SkyLightComponent.h"
#endif

namespace
{
UWorld* GuardCaptureWorld(UObject* Context)
{
#if WITH_EDITOR
    if (!IsInGameThread() || !IsRunningCommandlet() || !IsAllowCommandletRendering() || !GEngine)
        return nullptr;
    UWorld* World = GEngine->GetWorldFromContextObject(Context, EGetWorldErrorMode::ReturnNull);
    if (!World || World->WorldType != EWorldType::Editor || !World->Scene)
        return nullptr;
    return World;
#else
    return nullptr;
#endif
}
}

bool UAuditorCaptureV2Library::PrepareStaticCaptureWorld(UObject* WorldContextObject)
{
#if WITH_EDITOR
    UWorld* World = GuardCaptureWorld(WorldContextObject);
    if (!World) return false;
    FAssetCompilingManager::Get().FinishAllCompilation();
    USkyLightComponent::UpdateSkyCaptureContents(World);
    UReflectionCaptureComponent::UpdateReflectionCaptureContents(World, TEXT("AuditorCaptureV2"));
    World->SendAllEndOfFrameUpdates();
    return true;
#else
    return false;
#endif
}

int64 UAuditorCaptureV2Library::AdvanceStaticCaptureFrame(UObject* WorldContextObject)
{
    UWorld* World = GuardCaptureWorld(WorldContextObject);
    if (!World) return -1;
    World->Scene->IncrementFrameNumber();
    World->SendAllEndOfFrameUpdates();
    return static_cast<int64>(World->Scene->GetFrameNumber());
}
