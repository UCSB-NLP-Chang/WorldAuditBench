using UnrealBuildTool;
public class AtmosphericResidentialHouTarget : TargetRules {
    public AtmosphericResidentialHouTarget(TargetInfo Target) : base(Target) {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("AtmosphericResidentialHou");
    }
}
