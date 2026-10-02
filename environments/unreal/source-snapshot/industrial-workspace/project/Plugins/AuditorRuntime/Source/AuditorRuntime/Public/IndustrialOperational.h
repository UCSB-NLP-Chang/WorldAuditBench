#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "IndustrialOperational.generated.h"
UCLASS()
class AUDITORRUNTIME_API AIndustrialOperational : public AActor {
 GENERATED_BODY()
public:
 AIndustrialOperational();
 virtual void BeginPlay() override;
 virtual void Tick(float Dt) override;
 UPROPERTY(EditAnywhere) TObjectPtr<class UMaterialInterface> OffMaterial;
private:
 UPROPERTY() TObjectPtr<class AStaticMeshActor> Target;
 UPROPERTY() TObjectPtr<class ULightComponent> Light;
 UPROPERTY() TObjectPtr<class UMaterialInstanceDynamic> Panel;
 TArray<TObjectPtr<UMaterialInterface>> OriginalMaterials;
 FTransform Original; FVector Probe,Aim,InitialPosition; FRotator InitialRotation;
 FString CaseId,CapturePrefix; bool Bug=false,Testing=false,Ready=false,Moved=false,Changed=false,Done=false;
 float Age=0,Watch=0,PhaseAge=0,OriginalIntensity=0; int Phase=0; bool BeforeRecorded=false;
 void Finish(bool Pass,const FString& Detail);
};

