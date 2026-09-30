#pragma once
#include "CoreMinimal.h"
class AAuditorRegion;
class AAuditorCharacter;
namespace AuditorExploration {
bool Enabled();
void Expand(AAuditorRegion* Region);
bool Pending(UWorld* World);
void Apply(AAuditorCharacter* Pawn);
}
