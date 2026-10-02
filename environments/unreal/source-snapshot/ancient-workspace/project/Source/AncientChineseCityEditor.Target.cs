using UnrealBuildTool;
public class AncientChineseCityEditorTarget : TargetRules {
    public AncientChineseCityEditorTarget(TargetInfo Target) : base(Target) {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("AncientChineseCity");
    }
}
