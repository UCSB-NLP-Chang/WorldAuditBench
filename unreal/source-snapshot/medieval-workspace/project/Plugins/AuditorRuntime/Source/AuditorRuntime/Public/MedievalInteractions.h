#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MedievalInteractions.generated.h"
UCLASS()
class AUDITORRUNTIME_API AMedievalInteractions : public AActor {
 GENERATED_BODY()
public:
 AMedievalInteractions();
 void Configure(const FString& Task);
 virtual void Tick(float Dt) override;
 FString Interact();
 bool HandlesTest() const;
private:
 UPROPERTY() TObjectPtr<class AStaticMeshActor> Basket;
 UPROPERTY() TObjectPtr<class UBoxComponent> Body;
 UPROPERTY() TObjectPtr<class AActor> Windmill;
 UPROPERTY() TObjectPtr<class URotatingMovementComponent> Rotor;
 FRotator OriginalRate; FQuat WindmillSample; FVector WindmillBefore;
 bool WindmillSeen=false,WindmillChanged=false;
 UPROPERTY() TObjectPtr<class AStaticMeshActor> Door;
 UPROPERTY() TObjectPtr<class AStaticMeshActor> DoorOther;
 FTransform DoorOriginal,DoorOtherOriginal;
 FVector BasketCenter,BasketRestPoint,LastPushPosition;
 FString TaskId,CapturePath;
 bool CapturePending=false;int32 ExitCode=0;float CaptureAge=0;
 float SettleAge=0,DoorOtherAngle=85;
 bool OtherRequestedOpen=true;
 float Age=0,ReleaseAge=0,LastBounce=-10,DoorAngle=0,PhaseAge=0;
 int32 Bounces=0,Contacts=0,Phase=0;
 bool StairTest=false,ReachedLanding=false;
 bool Released=false,RequestedOpen=false,Seen=false,Left=false,Changed=false,Testing=false,CommonTest=false;
 UFUNCTION() void Contact(UPrimitiveComponent* Component,AActor* Other,UPrimitiveComponent* OtherComponent,FVector Impulse,const FHitResult& Hit);
 void TestStep(float Dt);
 void Finish(bool Pass,const FString& Detail);
};
