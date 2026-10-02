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
    static AActor* SpawnEditorActor(UWorld* World, TSubclassOf<AActor> ActorClass, const FTransform& Transform);
};
