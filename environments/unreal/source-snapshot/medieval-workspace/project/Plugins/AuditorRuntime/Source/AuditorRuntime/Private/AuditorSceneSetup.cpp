#include "AuditorSceneSetup.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"

AActor* UAuditorSceneSetup::SpawnEditorActor(UWorld* World, TSubclassOf<AActor> ActorClass, const FTransform& Transform)
{
#if WITH_EDITOR
    if (!World || World->WorldType != EWorldType::Editor || !ActorClass) return nullptr;
    FActorSpawnParameters Params;
    Params.OverrideLevel = World->PersistentLevel;
    Params.ObjectFlags |= RF_Transactional;
    Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    return World->SpawnActor<AActor>(ActorClass, Transform, Params);
#else
    return nullptr;
#endif
}

#if WITH_EDITOR
#include "AssetCompilingManager.h"
#include "Components/PrimitiveComponent.h"
#include "EngineUtils.h"
#include "MeshUtilities.h"
#endif
UStaticMesh* UAuditorSceneSetup::BakeParkedVehicle(const TArray<UMeshComponent*>& Components, const FString& PackageName)
{
#if WITH_EDITOR
    if (Components.IsEmpty() || !PackageName.StartsWith(TEXT("/Game/Auditor/MedievalVillage/"))) return nullptr;
    FAssetCompilingManager::Get().FinishAllCompilation();
    return FModuleManager::LoadModuleChecked<IMeshUtilities>(TEXT("MeshUtilities")).ConvertMeshesToStaticMesh(Components, FTransform::Identity, PackageName);
#else
    return nullptr;
#endif
}
void UAuditorSceneSetup::PrepareEditorCollision(UWorld* World)
{
#if WITH_EDITOR
    if (!World) return;
    FAssetCompilingManager::Get().FinishAllCompilation();
    World->UpdateWorldComponents(false, false);
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        TInlineComponentArray<UPrimitiveComponent*> Components;
        It->GetComponents(Components);
        for (UPrimitiveComponent* C : Components) C->RecreatePhysicsState();
    }
#endif
}
