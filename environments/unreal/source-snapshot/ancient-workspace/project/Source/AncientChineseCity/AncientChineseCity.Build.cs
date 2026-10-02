using UnrealBuildTool;
public class AncientChineseCity : ModuleRules {
    public AncientChineseCity(ReadOnlyTargetRules Target) : base(Target) {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AuditorRuntime" });
    }
}
