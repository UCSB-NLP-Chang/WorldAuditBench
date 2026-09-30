from pathlib import Path
import json,time,hashlib,shutil
B=Path('/Users/ziyan/3d-world-auditor/out/native-agents/batches/gemini-unreal-distance-ablation-20260921')
read=lambda n:json.loads((B/n).read_text())
p=read('progress.json');j=read('judge/results.json');c=read('cost-progress.json');f=read('batch.finished');lease=read('reservation.json')
assert len(p['tasks'])==252 and all(v['status'] in ('completed','failed') for v in p['tasks'].values())
assert not f.get('stopped') and not f.get('drained') and lease['status']=='released'
assert 'JUDGE PIPELINE FINISHED' in (B/'judge-pipeline.log').read_text()
rows={r['id']:r for r in j['tasks']};assert set(rows)==set(p['tasks'])
assert len(c['attempts'])==252 and c['incomplete_usage_attempts']==0 and not c['unknown_usage_attempts']
for k,v in p['tasks'].items():
 assert v['attempt']==1
 assert ('judge' in rows[k])==(v['status']=='completed'),k
assert read('final-runtime-audit.json')['passed']
s={'final':True,'batch':B.name,'recorded_at':time.time(),'assigned':252,'completed_reports':sum(v['status']=='completed' for v in p['tasks'].values()),'graded':j['graded'],'paper_failure_rule':'Unfinished assigned episodes count as failures; raw missing judge scores remain missing.','known_all_attempt_usd':c['known_all_attempt_usd'],'completed_attempt_usd':c['completed_attempt_usd'],'unknown_usage_attempts':0,'cost_excludes':['judge','infrastructure'],'far_reference':{'assigned':126,'successes':42,'success_rate':42/126},'arms':{},'source_judge_sha256':hashlib.sha256((B/'judge/results.json').read_bytes()).hexdigest(),'reservation_released':True,'batch_finished':f,'protocol':{'model':'gemini-3.8-flash','thinking_level':'medium','max_actions':40,'original_icl':True},'recording_incident':'Optional Gemini chat history was disabled by root disk exhaustion for 88 attempts. Required native records checked separately; original warnings and recovery audits retained.','recording_audits':['root-disk-chat-recording-impact.json','root-disk-required-record-verification.json','root-disk-recovery.json']}
for arm in ['near','medium']:
 rr=[r for r in rows.values() if r['id'].startswith(arm+'__')];aa=[a for a in c['attempts'] if a['case'].startswith(arm+'__')];n=sum('judge' in r for r in rr);success=sum(r.get('judge',{}).get('score',0) for r in rr)
 assert len(rr)==126 and len(aa)==126 and all(a['usage_complete'] for a in aa)
 a={'assigned':126,'completed_reports':n,'graded':n,'successes':success,'ungraded_failed_episode_ids':[r['id'] for r in rr if 'judge' not in r],'paper_success_rate':success/126,'paper_success_rate_percent':round(success/126*100,1),'difference_vs_far_pp':(success-42)/126*100,'known_all_attempt_usd':sum(x['estimated_usd'] for x in aa),'completed_attempt_usd':sum(x['estimated_usd'] for x in aa if x['status']=='completed'),'unknown_usage_attempts':0}
 s['arms'][arm]=a
 if arm=='medium':
  (B/'medium-final-execution-summary.json').write_text(json.dumps({'final_for_arm':True,'arm':arm,**a,'far_reference':s['far_reference'],'paper_failure_rule':s['paper_failure_rule'],'source_judge_sha256':s['source_judge_sha256']},indent=2)+'\n')
(B/'final-execution-summary.json').write_text(json.dumps(s,indent=2)+'\n')
print(json.dumps(s,indent=2))
