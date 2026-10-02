#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AuditorInvisibleBlocker.generated.h"

UCLASS()
class AUDITORRUNTIME_API AAuditorInvisibleBlocker : public AActor
{
    GENERATED_BODY()
public:
    AAuditorInvisibleBlocker();
    virtual void OnConstruction(const FTransform& Transform) override;
    UPROPERTY(EditAnywhere, Category="Blocker") FVector BoxExtent = FVector(50, 50, 100);
    UPROPERTY(EditAnywhere, Category="Blocker") FName CollisionProfile = TEXT("BlockAll");
private:
    UPROPERTY(VisibleAnywhere) TObjectPtr<class UBoxComponent> CollisionBox;
};
