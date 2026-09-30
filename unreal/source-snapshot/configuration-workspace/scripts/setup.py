import pathlib,json,subprocess
r=pathlib.Path('/home/ubuntu/unreal-auditor');w=r/'configuration-workspace';(w/'scripts').mkdir(parents=True,exist_ok=True);(w/'out').mkdir(exist_ok=True);(w/'backups').mkdir(exist_ok=True)
data={}
for f,workspace,project,maps in [
 ('subway','subway-workspace','projects/Subway/Subway.uproject',['/Game/Auditor/Subway/Platform']),
 ('indoor','indoor-workspace','indoor-workspace/project/AtmosphericResidentialHou.uproject',['/Game/Auditor/Regions/KitchenDining','/Game/Auditor/Regions/BedroomSuite']),
 ('ancient','ancient-workspace','ancient-workspace/project/AncientChineseCity.uproject',['/Game/Auditor/AncientCity/TeaHouse','/Game/Auditor/AncientCity/Courtyard']),
 ('industrial','industrial-workspace','industrial-workspace/project/FactoryEnvironmentCollect.uproject',['/Game/Auditor/Industrial/AssemblyHall']),
 ('medieval','medieval-workspace','medieval-workspace/project/MedievalVillage.uproject',['/Game/Auditor/MedievalVillage/Windmill']),
 ('urban','builds/core18-ue561-20260911','builds/core18-ue561-20260911/NYC_Building_Volume2.uproject',['/Game/Auditor/Migration/UE561/U012/R01/TaskMap_Candidate02'])]:
 data[f]={'workspace':str(r/workspace),'project':str(r/project),'maps':maps}
(w/'projects.json').write_text(json.dumps(data,indent=2));print('Configuration workspace ready')
