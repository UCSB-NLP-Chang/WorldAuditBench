"""Prepare an additive candidate from the CURRENT live review release."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

WORK = Path('/home/ubuntu/unreal-auditor/medieval-workspace')
SERVICE = WORK.parent / 'review-service'
STATE = SERVICE / 'state'

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    proof = json.loads((WORK / 'out/acceptance.json').read_text())
    assert proof['result'] == 'PASS' or ('--draft' in sys.argv and proof['result']=='DRAFT' and proof['native_tests_passed']==24 and proof['restoration_cycles_passed']==18), 'Publication requires completed packaged and rendered verification.'
    binary = Path(proof['binary'])
    assert digest(binary) == proof['binary_sha256']
    source = Path(subprocess.check_output(['systemctl', 'show', 'urban-review-pilot.service', '-p', 'WorkingDirectory', '--value'], text=True).strip())
    assert source.is_relative_to(SERVICE / 'releases')
    stage = SERVICE / 'staging' / proof['release_name']
    assert not stage.exists(), 'Use a fresh stage and rebase, never overwrite a candidate.'
    shutil.copytree(source, stage, ignore=shutil.ignore_patterns('__pycache__', 'prepared-state'))
    stage.chmod(0o700)
    env = WORK / 'environments/medieval-village'
    tasks = json.loads((env / 'tasks.json').read_text())['tasks']
    regions = json.loads((env / 'regions.json').read_text())['regions']
    scenes = json.loads((env / 'scene-descriptions.json').read_text())
    assert len(regions) == 2 and len(tasks) == 18
    manifest = json.loads((STATE / 'tasks.json').read_text())
    config = json.loads((STATE / 'runtime.json').read_text())
    assert not any(t.get('family') == 'medieval' for t in manifest['tasks'])
    previous_count = len(manifest['tasks'])
    keys = next(p['key_filter'] for p in config['launch_profiles'].values() if p.get('family') == 'subway')
    for i, region in enumerate(regions, 1):
        baseline = {'id':f'MVB{i:02}', 'title':region['name'], 'case_type':'baseline', 'rubrics_i18n':{
            'zh':{'expected':'村庄场景正常运行。','steps':'在区域内行走、观察并尝试说明中的交互。','criteria':'没有注入的异常。'},
            'en':{'expected':'The village scene behaves normally.','steps':'Explore the region and use the interactions described for it.','criteria':'No injected anomaly is present.'}}}
        for t in [baseline] + [t | {'case_type':'bug'} for t in tasks if t['region'] == region['id']]:
            map_name = region['map'] + ('?Task=' + t['id'] if t['case_type'] == 'bug' else '')
            entry = dict(id=t['id'],revision=1,map=map_name,sha256=digest(WORK/'project/Content'/(region['map'][6:]+'.umap')),
                build_sha256=proof['binary_sha256'],runtime_switch=True,family='medieval',environment='Medieval Village / '+region['name'],
                case_id=t['id'],case_path='/?case='+t['id'],case_type=t['case_type'],title=t['title'],rubrics_i18n=t['rubrics_i18n'],
                rubrics='\n'.join(t['rubrics_i18n'][lang]['criteria'] for lang in ('en','zh')))
            if 'subcategory' in t: entry['subcategory']=t['subcategory']
            manifest['tasks'].append(entry)
            config['launch_profiles'][map_name]=dict(binary=str(binary),build_sha256=proof['binary_sha256'],key_filter=keys,family='medieval',runtime_switch=True,game_args=proof['game_args'])
    assert len({t['id'] for t in manifest['tasks']}) == len(manifest['tasks'])
    (stage/'tasks.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    private=stage/'candidate-runtime.json';private.write_text(json.dumps(config,indent=2));private.chmod(0o600)
    server=stage/'server.py';text=server.read_text()
    matches=list(re.finditer(r"re\.fullmatch\(r'(\(\?:U\\d\{3\}[^']+)'",text))
    assert len(matches)==1, 'Review task validator changed; adapt the candidate explicitly.'
    match=matches[0];pattern=match[1];assert pattern.endswith(')')
    text=text[:match.start(1)]+pattern[:-1]+r'|MVB0[1-2]|MV(?:0[1-9]|1[0-8]))'+text[match.end(1):]
    marker=re.search(r"^( +)(if|elif) t\['id'\] in ancient:(.+)$",text,re.M);assert marker
    indent,word,body=marker.groups()
    replacement=(indent+word+" t['id'] in ('MVB01','MVB02'):allowed=('/Game/Auditor/MedievalVillage/'+{'MVB01':'Market','MVB02':'Windmill'}[t['id']],)\n"
                 +indent+"elif re.fullmatch(r'MV(?:0[1-9]|1[0-8])',t['id']):allowed=tuple('/Game/Auditor/MedievalVillage/'+region+'?Task='+t['id'] for region in ('Market','Windmill'))\n"
                 +indent+"elif t['id'] in ancient:"+body)
    text=text[:marker.start()]+replacement+text[marker.end():];ast.parse(text);server.write_text(text)
    app=stage/'static/app.js';text=app.read_text();assert 'medieval' not in text
    marker='let match;';assert marker in text
    text=text.replace(marker,marker+"if((match=/^MVB(\\d+)$/.exec(id)))return 'unreal_medieval_village_baseline_'+match[1].padStart(2,'0');if((match=/^MV(\\d+)$/.exec(id)))return 'unreal_medieval_village_bug_'+match[1].padStart(2,'0');",1)
    text=text.replace('ancient:3','ancient:3,medieval:6').replace("ancient:'Ancient Chinese City'","ancient:'Ancient Chinese City',medieval:'Medieval Village'")
    text,n=re.subn(r"for\(const key of \[('subway','indoor','urban','ancient'[^\]]*)\]\)",lambda m:"for(const key of ["+m[1]+",'medieval'])",text);assert n==1
    
    if "['ancient','industrial','rural'].includes(task.family)" in text:text=text.replace("['ancient','industrial','rural'].includes(task.family)","['ancient','industrial','rural','medieval'].includes(task.family)")
    elif "['ancient','industrial'].includes(task.family)" in text:text=text.replace("['ancient','industrial'].includes(task.family)","['ancient','industrial','medieval'].includes(task.family)")
    elif "['ancient','rural'].includes(task.family)" in text:text=text.replace("['ancient','rural'].includes(task.family)","['ancient','rural','medieval'].includes(task.family)")
    else:
        text,n=re.subn(r"if\((task\.family==='ancient'[^)]*)\)\{",lambda m:"if("+m[1]+"||task.family==='medieval'){",text,count=1);assert n==1
    match=re.search(r'const sceneDescriptions=(\[.*?\]);',text);assert match
    descriptions=json.loads(match[1]);descriptions.extend(scenes)
    text=text[:match.start(1)]+json.dumps(descriptions,ensure_ascii=False)+text[match.end(1):];app.write_text(text)
    page=stage/'static/index.html';text=page.read_text();marker='<option value="ancient">Ancient Chinese City</option>';assert marker in text
    page.write_text(text.replace(marker,marker+'<option value="medieval">Medieval Village</option>'))
    provenance=dict(source_release=str(source),source_files_sha256={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css') and '__pycache__' not in p.parts},source_state_sha256={n:digest(STATE/n) for n in ['tasks.json','runtime.json','service-env.json','participants.json']},binary_sha256=proof['binary_sha256'],previous_entries=previous_count,added_entries=len(tasks)+2,acceptance=proof)
    (stage/'medieval-provenance.json').write_text(json.dumps(provenance,indent=2))
    print('MEDIEVAL_REVIEW_CANDIDATE',stage,flush=True)

if __name__=='__main__':main()
