using UnrealBuildTool;
public class Subway : ModuleRules {
    public Subway(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AuditorRuntime" });
    }
}
