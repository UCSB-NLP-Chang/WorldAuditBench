// Shared rigid-pose recipe. Preserve mesh, scale, collision and authored support.
static void ApplyConfigurationPose(AStaticMeshActor* Actor, const TSharedPtr<FJsonObject>& Recipe)
{
 if (!Actor || FParse::Param(FCommandLine::Get(),TEXT("AuditorControl"))) return;
 const auto Before=Actor->GetStaticMeshComponent()->Bounds;
 const FVector LocalRotation=VectorField(Recipe,TEXT("configuration_rotation"));
 Actor->SetActorRotation(Actor->GetActorQuat()*FRotator(LocalRotation.X,LocalRotation.Y,LocalRotation.Z).Quaternion());
 const auto After=Actor->GetStaticMeshComponent()->Bounds;
 FVector Center=Before.Origin+VectorField(Recipe,TEXT("configuration_offset"));
 bool Seat=false;Recipe->TryGetBoolField(TEXT("configuration_seat"),Seat);
 if(Seat)Center.Z=Before.Origin.Z-Before.BoxExtent.Z+After.BoxExtent.Z;
 Actor->AddActorWorldOffset(Center-After.Origin);
}
static bool CheckConfigurationPose(AStaticMeshActor* Actor,const FTransform& Before,const TSharedPtr<FJsonObject>& Recipe,FString& Detail)
{
 if(!Actor){Detail=TEXT("Missing configuration target");return false;}
 const bool Control=FParse::Param(FCommandLine::Get(),TEXT("AuditorControl"));
 const FVector Axis=VectorField(Recipe,Control?TEXT("configuration_axis_clean"):TEXT("configuration_axis_bug"));
 const FVector LocalAxis=VectorField(Recipe,TEXT("configuration_local_axis"),FVector::UpVector);
 const FVector Actual=Actor->GetActorQuat().RotateVector(LocalAxis).GetSafeNormal();
 bool Pass=FVector::DotProduct(Actual,Axis.GetSafeNormal())>.995f && Actor->GetActorScale3D().Equals(Before.GetScale3D(),.001f) && Actor->GetActorEnableCollision();
 bool Seat=false;Recipe->TryGetBoolField(TEXT("configuration_seat"),Seat);
 if(Seat){
  const auto B=Actor->GetStaticMeshComponent()->Bounds;const FVector Bottom=B.Origin-FVector(0,0,B.BoxExtent.Z);
  FHitResult Hit;FCollisionQueryParams Q(SCENE_QUERY_STAT(ConfigurationSupport),true,Actor);
  Actor->GetWorld()->LineTraceSingleByChannel(Hit,Bottom+FVector(0,0,3),Bottom-FVector(0,0,8),ECC_Visibility,Q);
  Pass&=Hit.bBlockingHit&&FMath::Abs(Hit.ImpactPoint.Z-Bottom.Z)<4.f;
 }
 Detail=FString::Printf(TEXT("Rigid configuration %s: world axis %s, expected %s; original scale, solid collision and support checked"),Control?TEXT("clean"):TEXT("bug"),*Actual.ToString(),*Axis.ToString());return Pass;
}
