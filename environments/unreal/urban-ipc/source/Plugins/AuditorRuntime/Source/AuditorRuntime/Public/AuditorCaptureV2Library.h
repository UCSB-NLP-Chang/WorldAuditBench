#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AuditorCaptureV2Library.generated.h"

/** Explicit-call, commandlet-only static capture preparation. No map or gameplay routing. */
UCLASS()
class AUDITORRUNTIME_API UAuditorCaptureV2Library : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Wait for assets and initialize queued sky/reflection captures without saving or ticking gameplay. */
    UFUNCTION(BlueprintCallable, Category="Auditor|CaptureV2", meta=(WorldContext="WorldContextObject"))
    static bool PrepareStaticCaptureWorld(UObject* WorldContextObject);

    /** Advance only the rendering scene frame index. Returns -1 when guards reject the call. */
    UFUNCTION(BlueprintCallable, Category="Auditor|CaptureV2", meta=(WorldContext="WorldContextObject"))
    static int64 AdvanceStaticCaptureFrame(UObject* WorldContextObject);
};
