#include "AuditorExploration.h"
#include "AuditorPlaytest.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "HAL/PlatformMisc.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace AuditorExploration {
static TSharedPtr<FJsonObject> Policy;
static bool Loaded=false;
static FString Path;
static void Fail(const FString& Reason) {
 UE_LOG(LogTemp, Error, TEXT("AUDITOR_EXPLORATION_FAIL %s"), *Reason);
 FPlatformMisc::RequestExitWithStatus(false, 2);
}
bool Enabled() {
 if(!Loaded){Loaded=true;
  if(FParse::Value(FCommandLine::Get(),TEXT("AuditorExplorationPolicy="),Path)) {
   FString Text;
   if(!FFileHelper::LoadFileToString(Text,*Path)||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Policy)||!Policy.IsValid()) Fail(TEXT("Invalid exploration policy"));
  }
 }
 return !Path.IsEmpty();
}
static FVector Vec(const TSharedPtr<FJsonObject>& O,const TCHAR* K,FVector Default=FVector::ZeroVector) {
 const TArray<TSharedPtr<FJsonValue>>* A;
 if(!O||!O->TryGetArrayField(K,A)||A->Num()!=3)return Default;
 return FVector((*A)[0]->AsNumber(),(*A)[1]->AsNumber(),(*A)[2]->AsNumber());
}
static TSharedPtr<FJsonObject> Entry(UWorld* W) {
 if(!Enabled()||!Policy)return nullptr;
 FString Id;FParse::Value(FCommandLine::Get(),TEXT("AuditorExplorationTask="),Id);
 const auto* GM=W->GetAuthGameMode();
 const FString Option=GM?UGameplayStatics::ParseOption(GM->OptionsString,TEXT("Task")):FString();
 if(!Option.IsEmpty()&&Option!=TEXT("baseline"))Id=Option;
 const TSharedPtr<FJsonObject>* Tasks;
 const TSharedPtr<FJsonObject>* Result;
 if(Option==TEXT("baseline") && Policy->TryGetObjectField(TEXT("tasks"),Tasks)) {
  const FString Map=W->GetOutermost()->GetName();
  for(const auto& Pair:(*Tasks)->Values) {
   auto Candidate=Pair.Value->AsObject();FString CandidateMap,Case;
   if(Candidate && Candidate->TryGetStringField(TEXT("map"),CandidateMap) && Candidate->TryGetStringField(TEXT("case_type"),Case)
      && Case!=TEXT("bug") && CandidateMap==Map)return Candidate;
  }
 }
 if(Policy->TryGetObjectField(TEXT("tasks"),Tasks)&&(*Tasks)->TryGetObjectField(Id,Result))return *Result;
 Fail(TEXT("No entry for task ")+Id);return nullptr;
}
void Expand(AAuditorRegion* R){
 auto E=Entry(R->GetWorld());if(!E)return;
 const FVector OldMin=R->BoundsMin,OldMax=R->BoundsMax;
 R->BoundsMin=Vec(E,TEXT("bounds_min"),OldMin);R->BoundsMax=Vec(E,TEXT("bounds_max"),OldMax);
 if(R->BoundsMin.X>OldMin.X||R->BoundsMin.Y>OldMin.Y||R->BoundsMax.X<OldMax.X||R->BoundsMax.Y<OldMax.Y)Fail(TEXT("Policy shrinks existing region"));
}
bool Pending(UWorld* W){
 auto* P=Cast<AAuditorCharacter>(UGameplayStatics::GetPlayerPawn(W,0));
 return Enabled()&&(!P||!P->ActorHasTag(TEXT("exploration_ready")));
}
static TArray<TSharedPtr<FJsonValue>> Array(FVector V){return {MakeShared<FJsonValueNumber>(V.X),MakeShared<FJsonValueNumber>(V.Y),MakeShared<FJsonValueNumber>(V.Z)};}
void Apply(AAuditorCharacter* P){
 if(!P||!P->Controller||!P->Region||!Pending(P->GetWorld()))return;
 auto E=Entry(P->GetWorld());if(!E)return;
 UWorld* W=P->GetWorld();const FVector Old=P->GetActorLocation(),Focus=Vec(E,TEXT("focus"));
 double Step=100,Gain=300,MaxRoute=2400;E->TryGetNumberField(TEXT("grid_cm"),Step);E->TryGetNumberField(TEXT("gain_cm"),Gain);E->TryGetNumberField(TEXT("max_route_cm"),MaxRoute);
 const float Radius=P->GetCapsuleComponent()->GetScaledCapsuleRadius(),Half=P->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
 const float MaxStep=P->GetCharacterMovement()->MaxStepHeight;
 FCollisionQueryParams Q(SCENE_QUERY_STAT(ExplorationRoute),false,P);
 auto Floor=[&](FVector Guess,FVector& Ground){
  FHitResult H;
  if(!W->LineTraceSingleByChannel(H,Guess+FVector(0,0,40),Guess-FVector(0,0,Half+150),ECC_Pawn,Q)||H.ImpactNormal.Z<.71)return false;
  Ground=FVector(Guess.X,Guess.Y,H.ImpactPoint.Z+Half+2.2f);
  if(P->Region->Clearance(Ground,Radius+4)<0)return false;
  return !W->OverlapBlockingTestByChannel(Ground,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(Radius+1,Half-.5f),Q);
 };
 struct FNode{FVector P;int Parent;double Cost;FIntPoint Grid;};
 TArray<FNode> Nodes;FVector Root;
 bool UsedRegionRoot=false;
 if(!Floor(Old,Root)) {
  // Some legacy authored probes intersect a prop. Use the independently authored
  // clean region entrance as the route anchor, never an unchecked teleport.
  if(!Floor(Vec(E,TEXT("old_region_spawn")),Root)){Fail(TEXT("Neither original probe nor region entrance has clear supporting floor"));return;}
  UsedRegionRoot=true;
 }
 Nodes.Add({Root,-1,0,FIntPoint(0,0)});TSet<FIntPoint> Seen;Seen.Add(FIntPoint(0,0));
 int Best=-1;double BestScore=1e30;const double OldDistance=FVector::Dist2D(Old,Focus);const double Required=OldDistance+Gain;
 FVector Chosen;double Yaw=0;TArray<TSharedPtr<FJsonValue>> Route;
 const TArray<TSharedPtr<FJsonValue>>* Fixed;
 bool Frozen=E->TryGetArrayField(TEXT("spawn"),Fixed);
 if(Frozen){Chosen=Vec(E,TEXT("spawn"));E->TryGetNumberField(TEXT("yaw"),Yaw);FVector Check;
  if(!Floor(Chosen,Check)||FMath::Abs(Check.Z-Chosen.Z)>10){Fail(TEXT("Frozen spawn is obstructed"));return;}
 }else{
  if(!FParse::Param(FCommandLine::Get(),TEXT("AuditorExplorationPlan"))){Fail(TEXT("Unfrozen policy requires private planning mode"));return;}
  for(int Head=0;Head<Nodes.Num()&&Head<2400;Head++){
   const FNode N=Nodes[Head];const double Dist=FVector::Dist2D(N.P,Focus);
   if(Dist>=Required&&N.Cost>=Gain){const double Score=FMath::Abs(Dist-Required)+N.Cost*.1;
    if(Score<BestScore){Best=Head;BestScore=Score;}}
   if(N.Cost+Step>MaxRoute)continue;
   for(FIntPoint D:{FIntPoint(1,0),FIntPoint(-1,0),FIntPoint(0,1),FIntPoint(0,-1)}){
    const FIntPoint G=N.Grid+D;if(Seen.Contains(G))continue;
    FVector Dest;
    if(!Floor(N.P+FVector(D.X*Step,D.Y*Step,0),Dest)||FMath::Abs(Dest.Z-N.P.Z)>MaxStep)continue;
    FHitResult H;
    if(W->SweepSingleByChannel(H,N.P+FVector(0,0,MaxStep),Dest+FVector(0,0,MaxStep),FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(Radius+1,Half-.5f),Q))continue;
    Seen.Add(G);Nodes.Add({Dest,Head,N.Cost+Step,G});
   }
  }
  if(Best<0){Fail(FString::Printf(TEXT("No reachable farther spawn; old_distance=%.1f required=%.1f nodes=%d"),OldDistance,Required,Nodes.Num()));return;}
  Chosen=Nodes[Best].P;int I=Best;while(I>=0){Route.Add(MakeShared<FJsonValueArray>(Array(Nodes[I].P)));I=Nodes[I].Parent;}
  // Deterministic side-looking view, not a uniform instruction to turn around.
  FString Id;E->TryGetStringField(TEXT("id"),Id);
  uint32 H=0;for(TCHAR C:Id)H=H*31+uint32(C);
  const double Offset=110+(H%41);Yaw=(Focus-Chosen).Rotation().Yaw+((H&1)?Offset:-Offset);
 }
 P->GetCharacterMovement()->StopMovementImmediately();P->SetActorLocation(Chosen,false,nullptr,ETeleportType::TeleportPhysics);
 const FRotator Rotation(0,Yaw,0);P->SetActorRotation(Rotation);P->Controller->SetControlRotation(Rotation);
 P->Region->SpawnLocation=Chosen;P->Region->SpawnRotation=Rotation;P->Tags.AddUnique(TEXT("exploration_ready"));
 auto Report=MakeShared<FJsonObject>();FString Id;E->TryGetStringField(TEXT("id"),Id);
 Report->SetStringField(TEXT("id"),Id);Report->SetStringField(TEXT("status"),Frozen?TEXT("validated"):TEXT("planned"));Report->SetBoolField(TEXT("used_region_route_anchor"),UsedRegionRoot);Report->SetArrayField(TEXT("old_spawn"),Array(Old));Report->SetArrayField(TEXT("spawn"),Array(Chosen));Report->SetNumberField(TEXT("yaw"),Yaw);
 Report->SetNumberField(TEXT("old_distance_cm"),OldDistance);Report->SetNumberField(TEXT("distance_cm"),FVector::Dist2D(Chosen,Focus));Report->SetArrayField(TEXT("route_to_old_spawn"),Route);
 Report->SetArrayField(TEXT("bounds_min"),Array(P->Region->BoundsMin));Report->SetArrayField(TEXT("bounds_max"),Array(P->Region->BoundsMax));
 FString ReportPath;
 if(FParse::Value(FCommandLine::Get(),TEXT("AuditorExplorationReport="),ReportPath)){
  FString Text;FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&Text));FFileHelper::SaveStringToFile(Text,*ReportPath,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
 }
 UE_LOG(LogTemp,Display,TEXT("AUDITOR_EXPLORATION_READY id=%s old_distance=%.1f distance=%.1f yaw=%.1f frozen=%d"),*Id,OldDistance,FVector::Dist2D(Chosen,Focus),Yaw,Frozen);
}
}
