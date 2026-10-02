#include "AuditorResidentialRevision.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/PointLight.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "ResidentialTaskRevision.inl"

void ApplyResidentialRevision(UWorld* World, TArray<TSharedPtr<FJsonValue>>& Tasks)
{
    const FString Map = World->GetPackage()->GetName();
    if (Map != TEXT("/Game/Auditor/Regions/LivingRoom") && Map != TEXT("/Game/Auditor/Regions/KitchenDining") && Map != TEXT("/Game/Auditor/Regions/BedroomSuite")) return;
    TSharedPtr<FJsonObject> Revision;
    if (FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(FString(ResidentialTaskRevision)), Revision))
        Tasks = Revision->GetArrayField(TEXT("tasks"));

    // Runtime correction also updates already-cooked Mac maps, without adding
    // reflected properties that would break their unversioned serialization.
    if (FParse::Param(FCommandLine::Get(), TEXT("AuditorOriginalLighting"))) return;
    auto* Exposure = World->SpawnActor<APostProcessVolume>();
    Exposure->bUnbound = true;
    Exposure->Priority = 1000;
    Exposure->Settings.bOverride_AutoExposureBias = true;
    Exposure->Settings.AutoExposureBias = -0.7f;
    Exposure->Settings.bOverride_BloomIntensity = true;
    Exposure->Settings.BloomIntensity = 0.15f;
    for (TActorIterator<APointLight> It(World); It; ++It)
    {
        const FVector P = It->GetActorLocation();
        if (P.X > -1700 && P.X < 200 && P.Y > -1300 && P.Y < -300)
            It->GetLightComponent()->SetVisibility(false);
    }
    auto Find = [&](const TCHAR* Name) -> AStaticMeshActor*
    {
        const FName Tag(*(FString(TEXT("auditor_actor:")) + Name));
        for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
            if (It->ActorHasTag(Tag)) return *It;
        return nullptr;
    };
    auto Pendant = [&](FVector Location) -> AStaticMeshActor*
    {
        auto* Source = Find(TEXT("StaticMeshActor_933"));
        if (!Source) return nullptr;
        auto* Lamp = World->SpawnActor<AStaticMeshActor>();
        Lamp->SetMobility(EComponentMobility::Movable);
        auto* Mesh = Lamp->GetStaticMeshComponent();
        Mesh->SetStaticMesh(Source->GetStaticMeshComponent()->GetStaticMesh());
        for (int32 I=0; I<Source->GetStaticMeshComponent()->GetNumMaterials(); ++I)
            Mesh->SetMaterial(I, Source->GetStaticMeshComponent()->GetMaterial(I));
        Lamp->SetActorTransform(Source->GetActorTransform());
        Lamp->SetActorLocation(Location);
        return Lamp;
    };
    auto Illuminate = [&](AStaticMeshActor* Fixture, float Lumens)
    {
        if (!Fixture) return;
        // One emitter approximates a multi-bulb fixture. Its whole-mesh shadow
        // otherwise produces an oversized, misleading silhouette on the ceiling.
        // Room geometry still casts shadows from this light.
        Fixture->GetStaticMeshComponent()->SetCastShadow(false);
        const auto Bounds = Fixture->GetStaticMeshComponent()->Bounds;
        // Just below the shade opening, aligned with the visible fixture.
        const FVector Position(Bounds.Origin.X, Bounds.Origin.Y, Bounds.Origin.Z-Bounds.BoxExtent.Z-2);
        auto* Light = World->SpawnActor<APointLight>(Position, FRotator::ZeroRotator);
        auto* C = CastChecked<UPointLightComponent>(Light->GetLightComponent());
        C->SetMobility(EComponentMobility::Movable);
        C->SetIntensityUnits(ELightUnits::Lumens);
        C->SetIntensity(Lumens * 0.55f);
        C->SetAttenuationRadius(650);
        C->SetSourceRadius(15);
        C->SetSoftSourceRadius(10);
        C->SetCastShadows(true);
        C->SetUseTemperature(true);
        C->SetTemperature(4500);
        C->SetVolumetricScatteringIntensity(0);
        Light->AttachToActor(Fixture, FAttachmentTransformRules::KeepWorldTransform);
        UE_LOG(LogTemp, Display, TEXT("AUDITOR_FIXTURE_LIGHT fixture=%s position=%s lumens=%.0f"), *Fixture->GetName(), *Position.ToString(), C->Intensity);
    };
    Illuminate(Find(TEXT("StaticMeshActor_493")), 1500);
    Illuminate(Find(TEXT("StaticMeshActor_495")), 1200);
    Illuminate(Pendant(FVector(-110,-1030,435)), 1800);
    Illuminate(Find(TEXT("StaticMeshActor_500")), 1400);
    Illuminate(Pendant(FVector(-1300,-1080,736)), 1000);
}
