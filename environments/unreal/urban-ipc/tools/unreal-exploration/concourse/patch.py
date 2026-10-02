from pathlib import Path
import shutil
w=Path("/home/ubuntu/unreal-auditor/subway-workspace/review-concourse-20260917");p=Path("/home/ubuntu/unreal-auditor/projects/Subway/Plugins/AuditorRuntime/Source/AuditorRuntime/Private/AuditorTasks.cpp");s=p.read_text();assert "FountainBackfaceDraft" not in s;shutil.copy2(p,w/"before/AuditorTasks.cpp")
needle="    const FString Name = Spec->GetStringField(TEXT(\"target\"));"
new="""    // FountainBackfaceDraft: restore the original one-sided surfaces only for
    // this explicit draft task. Clean cases use the repaired cooked materials.
    if (Kind == TEXT("fountain_backface"))
    {
        AActor* Fountain = nullptr;
        for (TActorIterator<AActor> It(GetWorld()); It; ++It)
            if (It->GetName() == Spec->GetStringField(TEXT("actor_target"))) { Fountain = *It; break; }
        if (!Fountain) { FinishTest(false, TEXT("Missing fountain feature")); return false; }
        TArray<UStaticMeshComponent*> Meshes; Fountain->GetComponents(Meshes);
        const auto& Materials = Spec->GetArrayField(TEXT("materials"));
        if (Meshes.Num() != 1 || Materials.Num() != Meshes[0]->GetNumMaterials())
        { FinishTest(false, TEXT("Fountain material slots differ")); return false; }
        for (int32 I = 0; I < Materials.Num(); ++I)
        {
            auto* Material = LoadObject<UMaterialInterface>(nullptr, *Materials[I]->AsString());
            if (!Material) { FinishTest(false, TEXT("Missing original fountain material")); return false; }
            Meshes[0]->SetMaterial(I, Material);
        }
        UE_LOG(LogTemp, Display, TEXT("AUDITOR_TASK_READY id=%s kind=fountain_backface"), *ActiveId);
        return true;
    }
"""
assert s.count(needle)==1;p.write_text(s.replace(needle,new+needle))
