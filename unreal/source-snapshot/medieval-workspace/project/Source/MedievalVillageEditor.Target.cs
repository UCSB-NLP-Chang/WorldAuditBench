using UnrealBuildTool;
public class MedievalVillageEditorTarget : TargetRules {
    public MedievalVillageEditorTarget(TargetInfo Target) : base(Target) {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("MedievalVillage");
    }
}
