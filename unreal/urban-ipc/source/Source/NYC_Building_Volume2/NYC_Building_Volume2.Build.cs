using UnrealBuildTool;
public class NYC_Building_Volume2 : ModuleRules {
    public NYC_Building_Volume2(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AuditorRuntime" });
    }
}
