#include "AuditorTasks.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Animation/SkeletalMeshActor.h"
#include "EngineUtils.h"

namespace {
TArray<USkeletalMeshComponent*> Escalators(UWorld* World)
{
    TArray<USkeletalMeshComponent*> Result;
    for (TActorIterator<ASkeletalMeshActor> It(World); It; ++It)
    {
        auto* Mesh = It->GetSkeletalMeshComponent();
        if (Mesh && Mesh->GetSkeletalMeshAsset() && Mesh->GetSkeletalMeshAsset()->GetName().Equals(TEXT("SK_Escalator"), ESearchCase::IgnoreCase))
            Result.Add(Mesh);
    }
    return Result;
}
}

bool AAuditorTasks::ConfigureEscalators(bool SameDirection)
{
    const auto Meshes = Escalators(GetWorld());
    UAnimationAsset* Up = nullptr;
    for (auto* Mesh : Meshes)
        if (auto* Instance = Mesh->GetSingleNodeInstance())
            if (auto* Asset = Instance->GetCurrentAsset(); Asset && Asset->GetName() == TEXT("Anim_Escalator_02")) Up = Asset;
    if (Meshes.Num() != 8 || !Up) return false;
    for (auto* Mesh : Meshes)
    {
        // Keep off-screen pairs running too; selecting another task reloads their authored animations.
        Mesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
        if (SameDirection)
        {
            Mesh->PlayAnimation(Up, true);
            Mesh->SetPlayRate(1.0f);
        }
    }
    return true;
}

void AAuditorTasks::TestEscalators(bool SameDirection)
{
    const auto Meshes = Escalators(GetWorld());
    int32 Up = 0, Down = 0;
    bool Playing = true;
    for (auto* Mesh : Meshes)
    {
        Playing &= Mesh->IsPlaying() && Mesh->GetBoneIndex(TEXT("Object051")) != INDEX_NONE;
        const float SavedPosition = Mesh->GetPosition();
        Mesh->SetPosition(.15f, false);
        Mesh->TickAnimation(0.0f, false);
        Mesh->RefreshBoneTransforms();
        const double Before = Mesh->GetSocketLocation(TEXT("Object051")).Z;
        // Evaluate the actual assigned clip at the next time, including the component's play rate.
        Mesh->TickAnimation(.15f, false);
        Mesh->RefreshBoneTransforms();
        const double Delta = Mesh->GetSocketLocation(TEXT("Object051")).Z - Before;
        Up += Delta > 1.0;
        Down += Delta < -1.0;
        UE_LOG(LogTemp, Display, TEXT("AUDITOR_ESCALATOR_MOTION actor=%s delta_z=%.3f playing=%d"), *Mesh->GetOwner()->GetName(), Delta, Mesh->IsPlaying());
        Mesh->SetPosition(SavedPosition, false);
    }
    FinishTest(Meshes.Num() == 8 && Playing && (SameDirection ? Up == 8 && Down == 0 : Up == 4 && Down == 4),
        FString::Printf(TEXT("Measured tread-bone motion on %d escalators: %d up, %d down; playing=%d"), Meshes.Num(), Up, Down, Playing));
}
