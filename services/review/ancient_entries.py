"""Build the fourth-family manifest projection from its authoritative A10 catalog."""
from pathlib import Path
import hashlib,json

def build_ancient_entries(root=Path('/home/ubuntu/unreal-auditor')):
    work=root/'ancient-workspace';env=work/'environments/ancient-chinese-city'
    catalog=json.loads((env/'tasks.json').read_text())['tasks'];regions=json.loads((env/'regions.json').read_text())['regions']
    binary=work/'dist/ancient-era-20260913-v1/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity'
    def digest(p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
        return h.hexdigest()
    build_sha=digest(binary);entries=[];profiles={}
    keys='M,N,P,F1,F2,F3,F4,Zero,One,Two,Three,Four,Five,Six,Seven,Eight,Nine,NumPadZero,NumPadOne,NumPadTwo,NumPadThree,NumPadFour,NumPadFive,NumPadSix,NumPadSeven,NumPadEight,NumPadNine,Tilde,Escape'
    for i,reg in enumerate(regions,1):
        sha=digest(work/'project/Content'/(reg['map'][6:]+'.umap'))
        baseline={'id':f'AB{i:02}','case_type':'baseline','title':reg['name'],'rubrics_i18n':{'en':{'expected':'The scene behaves normally without an injected bug.','steps':'Explore the scene and try the interactions described in Scene description.','criteria':'No injected anomaly is present.'},'zh':{'expected':'场景应正常运行，没有注入的错误。','steps':'探索场景并尝试场景描述中的交互。','criteria':'没有注入的异常。'}}}
        for task in [baseline]+[t|{'case_type':'bug'} for t in catalog if t['region']==reg['id']]:
            id=task['id'];map=reg['map']+('?Task='+id if task['case_type']=='bug' else '')
            entry={'id':id,'revision':1,'map':map,'sha256':sha,'build_sha256':build_sha,'runtime_switch':True,'family':'ancient','environment':'Ancient Chinese City / '+reg['name'],'case_id':id,'case_path':'/?case='+id,'case_type':task['case_type'],'title':task['title'],'rubrics_i18n':task['rubrics_i18n'],'rubrics':task['rubrics_i18n']['en']['criteria']+'\n'+task['rubrics_i18n']['zh']['criteria']}
            if 'subcategory' in task:entry['subcategory']=task['subcategory']
            entries.append(entry)
            profiles[map]={'binary':str(binary),'build_sha256':build_sha,'key_filter':keys,'family':'ancient','runtime_switch':True,'game_args':['-vulkan','-sm6','-PixelStreamingWebRTCMaxFps=30','-ExecCmds=t.MaxFPS 30']}
    assert len(entries)==len(catalog)+len(regions) and len({e['id'] for e in entries})==len(entries)
    return entries,profiles
