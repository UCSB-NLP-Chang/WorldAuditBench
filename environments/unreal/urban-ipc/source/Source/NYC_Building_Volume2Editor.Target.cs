using UnrealBuildTool;
public class NYC_Building_Volume2EditorTarget : TargetRules {
    public NYC_Building_Volume2EditorTarget(TargetInfo Target) : base(Target) {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("NYC_Building_Volume2");
    }
}
