using UnrealBuildTool;
public class AtmosphericResidentialHou : ModuleRules {
    public AtmosphericResidentialHou(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AuditorRuntime" });
    }
}
