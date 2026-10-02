using UnrealBuildTool;
public class AtmosphericResidentialHouEditorTarget : TargetRules {
    public AtmosphericResidentialHouEditorTarget(TargetInfo Target) : base(Target) {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("AtmosphericResidentialHou");
    }
}
