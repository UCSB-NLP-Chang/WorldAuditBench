using UnrealBuildTool;
public class MedievalVillage : ModuleRules {
    public MedievalVillage(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AuditorRuntime" });
    }
}
