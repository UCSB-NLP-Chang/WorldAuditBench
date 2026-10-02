#include "AuditorInvisibleBlocker.h"
#include "Components/BoxComponent.h"

AAuditorInvisibleBlocker::AAuditorInvisibleBlocker()
{
    PrimaryActorTick.bCanEverTick = false;
    CollisionBox = CreateDefaultSubobject<UBoxComponent>(TEXT("CollisionBox"));
    RootComponent = CollisionBox;
    CollisionBox->SetHiddenInGame(true);
    CollisionBox->SetVisibility(false);
    CollisionBox->SetGenerateOverlapEvents(false);
    CollisionBox->SetCanEverAffectNavigation(false);
}
void AAuditorInvisibleBlocker::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    CollisionBox->SetBoxExtent(BoxExtent);
    CollisionBox->SetCollisionProfileName(CollisionProfile);
    CollisionBox->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    CollisionBox->SetCollisionResponseToAllChannels(ECR_Ignore);
    CollisionBox->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
}
