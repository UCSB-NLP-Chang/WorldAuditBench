#include "AuditorCollisionProbe.h"
#include "AuditorPlaytest.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
namespace {
 FVector CollisionVec(const TSharedPtr<FJsonObject>& O,const TCHAR* Key) { const auto& A=O->GetArrayField(Key);return FVector(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber()); }
 TArray<TSharedPtr<FJsonValue>> CollisionArr(FVector V) { return {MakeShared<FJsonValueNumber>(V.X),MakeShared<FJsonValueNumber>(V.Y),MakeShared<FJsonValueNumber>(V.Z)}; }
}
void UAuditorCollisionProbe::OnWorldBeginPlay(UWorld& InWorld)
{
 Super::OnWorldBeginPlay(InWorld);
 FString Path,Text;
 if(!InWorld.IsGameWorld() || !FParse::Value(FCommandLine::Get(),TEXT("AuditorCollisionProbe="),Path))return;
 if(!FFileHelper::LoadFileToString(Text,*Path) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Spec) || !Spec.IsValid()) { FPlatformMisc::RequestExitWithStatus(false,2);return; }
 Output=Spec->GetStringField(TEXT("output"));IFileManager::Get().MakeDirectory(*FPaths::GetPath(Output),true);
 if(InWorld.GetOutermost()->GetName()!=Spec->GetStringField(TEXT("map"))) {Finish(false,TEXT("wrong runtime map"));return;}
 bActive=true;
}
void UAuditorCollisionProbe::Tick(float DeltaTime)
{
 if(!bActive)return;Age+=DeltaTime;Wait+=DeltaTime;
 if(Age>60){Finish(false,TEXT("simulation timeout"));return;}
 if(Age<2 || Wait<0.25)return;
 auto C=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(GetWorld(),0));
 if(!C)return;
 auto Capsule=C->GetCapsuleComponent();auto Movement=C->GetCharacterMovement();
 if(!Capsule || !Movement || C->GetRootComponent()!=Capsule){Finish(false,TEXT("actual AuditorCharacter root capsule missing"));return;}
 if(!FMath::IsNearlyEqual(Capsule->GetScaledCapsuleRadius(),30.f,.01f) || !FMath::IsNearlyEqual(Capsule->GetScaledCapsuleHalfHeight(),90.f,.01f)) {Finish(false,TEXT("unexpected real player capsule dimensions"));return;}
 const auto& Routes=Spec->GetArrayField(TEXT("routes"));
 if(Index>=Routes.Num()){Finish(bAllPassed,TEXT("complete"));return;}
 auto Route=Routes[Index]->AsObject();const FVector Start=CollisionVec(Route,TEXT("start")),End=CollisionVec(Route,TEXT("end"));
 Movement->StopMovementImmediately();Movement->DisableMovement();
 C->SetActorLocation(Start,false,nullptr,ETeleportType::TeleportPhysics);
 // This moves the REAL root capsule through the cooked scene using its actual
 // object type and collision response settings. No synthetic query capsule,
 // trace-profile substitution, resized pawn, gravity, sliding, or input simulation.
 FHitResult Hit;
 C->SetActorLocation(End,true,&Hit,ETeleportType::None);
 const FVector Actual=C->GetActorLocation();const bool Expected=Route->GetBoolField(TEXT("expected_hit"));
 const bool Pass=Hit.bBlockingHit==Expected && !Hit.bStartPenetrating && (Expected ? FVector::Dist(Actual,End)>1.0 : Actual.Equals(End,.1));
 auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("name"),Route->GetStringField(TEXT("name")));
 R->SetArrayField(TEXT("start"),CollisionArr(Start));R->SetArrayField(TEXT("requested_end"),CollisionArr(End));R->SetArrayField(TEXT("actual_end"),CollisionArr(Actual));
 R->SetBoolField(TEXT("expected_hit"),Expected);R->SetBoolField(TEXT("blocking_hit"),Hit.bBlockingHit);R->SetBoolField(TEXT("start_penetrating"),Hit.bStartPenetrating);R->SetBoolField(TEXT("passed"),Pass);
 R->SetNumberField(TEXT("hit_time"),Hit.Time);R->SetNumberField(TEXT("hit_distance"),Hit.Distance);R->SetNumberField(TEXT("radius"),Capsule->GetScaledCapsuleRadius());R->SetNumberField(TEXT("half_height"),Capsule->GetScaledCapsuleHalfHeight());
 R->SetStringField(TEXT("pawn_class"),C->GetClass()->GetPathName());R->SetStringField(TEXT("capsule_collision_profile"),Capsule->GetCollisionProfileName().ToString());
 R->SetStringField(TEXT("hit_actor"),Hit.GetActor()?Hit.GetActor()->GetPathName():TEXT(""));R->SetStringField(TEXT("hit_component"),Hit.GetComponent()?Hit.GetComponent()->GetPathName():TEXT(""));
 R->SetNumberField(TEXT("simulation_seconds"),Age);Results.Add(MakeShared<FJsonValueObject>(R));bAllPassed &= Pass;Index++;Wait=0;
}
void UAuditorCollisionProbe::Finish(bool Passed,const FString& Reason)
{
 bActive=false;auto Report=MakeShared<FJsonObject>();Report->SetBoolField(TEXT("passed"),Passed);Report->SetStringField(TEXT("reason"),Reason);
 Report->SetStringField(TEXT("mode"),TEXT("cooked_actual_player_root_capsule_swept_movement"));Report->SetBoolField(TEXT("walking_input_verified"),false);Report->SetStringField(TEXT("map"),GetWorld()?GetWorld()->GetOutermost()->GetName():TEXT(""));Report->SetArrayField(TEXT("routes"),Results);
 FString Text;FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&Text));
 const bool Saved=!Output.IsEmpty() && FFileHelper::SaveStringToFile(Text,*Output);
 FPlatformMisc::RequestExitWithStatus(false,Passed && Saved?0:2);
}
