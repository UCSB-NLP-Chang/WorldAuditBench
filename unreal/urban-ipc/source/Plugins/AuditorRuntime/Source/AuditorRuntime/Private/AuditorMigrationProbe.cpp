#include "AuditorMigrationProbe.h"
#include "AuditorStateScenario.h"
#include "Components/MeshComponent.h"
#include "Camera/CameraComponent.h"
#include "Materials/MaterialInterface.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "HighResScreenshot.h"
#include "UnrealClient.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
namespace {
 FVector Vec(const TSharedPtr<FJsonObject>& O,const TCHAR* Key) { const auto& A=O->GetArrayField(Key);return FVector(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber()); }
 TArray<TSharedPtr<FJsonValue>> Arr(FVector V) { return {MakeShared<FJsonValueNumber>(V.X),MakeShared<FJsonValueNumber>(V.Y),MakeShared<FJsonValueNumber>(V.Z)}; }
 FString Mat(AActor* A) { auto M=A->FindComponentByClass<UMeshComponent>();return M && M->GetMaterial(0) ? M->GetMaterial(0)->GetPathName() : TEXT(""); }
}
void UAuditorMigrationProbe::OnWorldBeginPlay(UWorld& InWorld)
{
 Super::OnWorldBeginPlay(InWorld);
 FString Path,Text;
 if(!InWorld.IsGameWorld() || !FParse::Value(FCommandLine::Get(),TEXT("AuditorMigrationProbe="),Path))return;
 if(!FFileHelper::LoadFileToString(Text,*Path) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Spec) || !Spec.IsValid()) { FPlatformMisc::RequestExitWithStatus(false,2);return; }
 Output=Spec->GetStringField(TEXT("output")); IFileManager::Get().MakeDirectory(*Output,true);
 FString Task;Spec->TryGetStringField(TEXT("task"),Task);
 for(TActorIterator<AAuditorStateScenario> It(&InWorld);It;++It) if(It->TaskId==Task){Scenario=*It;break;}
 const bool WantState=Spec->GetBoolField(TEXT("state"));
 if(WantState && (!Scenario.IsValid() || !Scenario->TargetActor)) { Finish(false,TEXT("missing scenario target"));return; }
 if(Scenario.IsValid()) { auto A=Scenario->TargetActor;InitialLocation=A->GetActorLocation();InitialRotation=A->GetActorRotation();InitialHidden=A->IsHidden();InitialCollision=A->GetActorEnableCollision();InitialMaterial=Mat(A); }
 bActive=true;
}
bool UAuditorMigrationProbe::SetStep()
{
 auto Pawn=UGameplayStatics::GetPlayerPawn(GetWorld(),0);auto PC=UGameplayStatics::GetPlayerController(GetWorld(),0);
 if(!Pawn || !PC)return false;
 auto Step=Spec->GetArrayField(TEXT("steps"))[Index]->AsObject();
 auto Camera=Pawn->FindComponentByClass<UCameraComponent>();
 FVector Position=Vec(Step,TEXT("position"));
 if(Camera && Step->HasField(TEXT("camera_position"))) Position=Vec(Step,TEXT("camera_position"))-(Camera->GetComponentLocation()-Pawn->GetActorLocation());
 Pawn->SetActorLocation(Position,false,nullptr,ETeleportType::TeleportPhysics);
 if(auto C=Cast<ACharacter>(Pawn)) {C->GetCharacterMovement()->StopMovementImmediately();C->GetCharacterMovement()->DisableMovement();}
 FVector View=Camera ? Camera->GetComponentLocation() : Pawn->GetPawnViewLocation();PC->SetControlRotation((Vec(Step,TEXT("aim"))-View).Rotation());
 StageAge=0;bPositioned=true;bRequested=false;return true;
}
bool UAuditorMigrationProbe::RecordStep()
{
 auto Step=Spec->GetArrayField(TEXT("steps"))[Index]->AsObject();
 auto R=MakeShared<FJsonObject>();R->SetNumberField(TEXT("simulation_seconds"),Age);R->SetNumberField(TEXT("step"),Index);R->SetStringField(TEXT("name"),Step->GetStringField(TEXT("name")));
 auto Pawn=UGameplayStatics::GetPlayerPawn(GetWorld(),0);R->SetArrayField(TEXT("pawn_position"),Arr(Pawn->GetActorLocation()));
 FVector View;FRotator Rot;UGameplayStatics::GetPlayerController(GetWorld(),0)->GetPlayerViewPoint(View,Rot);R->SetArrayField(TEXT("view_position"),Arr(View));
 bool Pass=true;
 if(Scenario.IsValid()) {
  auto A=Scenario->TargetActor;FString Expect=Step->GetStringField(TEXT("expect"));
  R->SetArrayField(TEXT("target_location"),Arr(A->GetActorLocation()));R->SetBoolField(TEXT("hidden"),A->IsHidden());R->SetBoolField(TEXT("collision"),A->GetActorEnableCollision());R->SetStringField(TEXT("material"),Mat(A));R->SetStringField(TEXT("expect"),Expect);
  if(Expect==TEXT("initial")) Pass=A->GetActorLocation().Equals(InitialLocation,.1) && A->GetActorRotation().Equals(InitialRotation,.1) && A->IsHidden()==InitialHidden && A->GetActorEnableCollision()==InitialCollision && Mat(A)==InitialMaterial;
  else if(Expect==TEXT("applied")) {
   if(Scenario->Effect==EAuditorScenarioEffect::Hide)Pass=A->IsHidden() && (!Scenario->DisableCollisionWhenHidden || !A->GetActorEnableCollision()) && A->GetActorLocation().Equals(InitialLocation,.1);
   else if(Scenario->Effect==EAuditorScenarioEffect::TransformOffset)Pass=A->GetActorLocation().Equals(InitialLocation+Scenario->LocationOffset,.1) && A->GetActorRotation().Equals(InitialRotation+Scenario->RotationOffset,.1) && !A->IsHidden() && A->GetActorEnableCollision()==InitialCollision && Mat(A)==InitialMaterial;
   else if(Scenario->Effect==EAuditorScenarioEffect::Material)Pass=Scenario->ReplacementMaterial && Mat(A)==Scenario->ReplacementMaterial->GetPathName() && Mat(A)!=InitialMaterial && A->GetActorLocation().Equals(InitialLocation,.1) && A->GetActorEnableCollision()==InitialCollision && !A->IsHidden();
   else Pass=false;
  } else Pass=false;
 }
 R->SetBoolField(TEXT("passed"),Pass);Trace.Add(MakeShared<FJsonValueObject>(R));return Pass;
}
void UAuditorMigrationProbe::Tick(float DeltaTime)
{
 if(!bActive)return;Age+=DeltaTime;StageAge+=DeltaTime;
 if(Age>180){Finish(false,TEXT("simulation timeout"));return;}
 // Allow the character to finish its one-time possession/view initialization.
 if(!bPositioned){if(Age>=1.0f)SetStep();return;}
 auto Step=Spec->GetArrayField(TEXT("steps"))[Index]->AsObject();
 FString Shot=Output/TEXT("step-")+FString::FromInt(Index)+TEXT(".png");
 if(StageAge>=8 && !bRequested){if(!RecordStep()){Finish(false,TEXT("state expectation mismatch"));return;}FScreenshotRequest::RequestScreenshot(Shot,false,false);bRequested=true;}
 if(bRequested && StageAge>=9 && IFileManager::Get().FileExists(*Shot)) {
  ++Index;if(Index>=Spec->GetArrayField(TEXT("steps")).Num()){Finish(true,TEXT("completed"));return;}bPositioned=false;
 }
 if(StageAge>45){Finish(false,TEXT("GPU screenshot timeout"));}
}
void UAuditorMigrationProbe::Finish(bool Success,const FString& Reason)
{
 bActive=false;auto R=MakeShared<FJsonObject>();R->SetBoolField(TEXT("passed"),Success);R->SetStringField(TEXT("reason"),Reason);R->SetArrayField(TEXT("trace"),Trace);R->SetBoolField(TEXT("human_acceptance"),false);R->SetStringField(TEXT("method"),TEXT("packaged GPU, simulation-time route staging; teleport positions, real scenario Tick and sight traces; not human navigation proof"));
 FString Text;FJsonSerializer::Serialize(R,TJsonWriterFactory<>::Create(&Text));FFileHelper::SaveStringToFile(Text,*(Output/TEXT("result.json")));
 UE_LOG(LogTemp,Display,TEXT("AUDITOR_MIGRATION_PROBE %s %s"),Success?TEXT("PASS"):TEXT("FAIL"),*Reason);FPlatformMisc::RequestExitWithStatus(false,Success?0:1);
}
