using UnrealBuildTool;
public class MedievalVillageTarget : TargetRules {
    public MedievalVillageTarget(TargetInfo Target) : base(Target) {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("MedievalVillage");
    }
}
