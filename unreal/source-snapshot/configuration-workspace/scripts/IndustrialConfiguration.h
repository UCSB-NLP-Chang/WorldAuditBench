#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "IndustrialConfiguration.generated.h"
UCLASS()
class AUDITORRUNTIME_API AIndustrialConfiguration : public AActor {
 GENERATED_BODY()
public:
 AIndustrialConfiguration();
 virtual void BeginPlay() override;
 virtual void Tick(float DeltaSeconds) override;
private:
 UPROPERTY() TObjectPtr<AActor> Robot;
 UPROPERTY() TObjectPtr<class UStaticMeshComponent> Effector;
 UPROPERTY() TObjectPtr<class USkeletalMeshComponent> Arm;
 UPROPERTY() TObjectPtr<class AStaticMeshActor> Tray;
 UPROPERTY() TObjectPtr<class UParticleSystemComponent> Sparks;
 FVector WeldPoint,FirstBonePosition;
 FName TipBone;
 FString TaskId,CapturePath;
 float Age=0,Motion=0,CaptureAge=0;int Samples=0;bool Test=false,Done=false,Capturing=false,Control=false;
 void Finish(bool Pass,const FString& Detail);
};
