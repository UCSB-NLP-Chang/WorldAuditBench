using UnrealBuildTool;
public class NYC_Building_Volume2Target : TargetRules {
    public NYC_Building_Volume2Target(TargetInfo Target) : base(Target) {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("NYC_Building_Volume2");
    }
}
