#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AuditorSceneSetup.generated.h"

/** Editor automation that does not depend on a rendered placement viewport. */
UCLASS()
class AUDITORRUNTIME_API UAuditorSceneSetup : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Auditor|Scene Setup")
    static void PrepareEditorCollision(UWorld* World);
    UFUNCTION(BlueprintCallable, Category="Auditor|Scene Setup")
    static AActor* SpawnEditorActor(UWorld* World, TSubclassOf<AActor> ActorClass, const FTransform& Transform);
    /** Bake an assembled vehicle in its reference pose for use as a parked prop. */
    UFUNCTION(BlueprintCallable, Category="Auditor|Scene Setup")
    static UStaticMesh* BakeParkedVehicle(const TArray<class UMeshComponent*>& Components, const FString& PackageName);
};
