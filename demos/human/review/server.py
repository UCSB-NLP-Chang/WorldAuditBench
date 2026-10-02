#!/usr/bin/env python3
"""Small single-process review coordinator. Mock is explicitly not a game stream."""
import base64, hashlib, hmac, http.cookies, json, os, pathlib, secrets, signal, sqlite3, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from taxonomy import classify, summarize
from browser_runtime import BrowserSessions, is_browser, validate_browser_task

BASE = pathlib.Path(__file__).resolve().parent
VERDICTS = {'found', 'not_found', 'uncertain', 'technical_issue'}
ACTIVE = ('queued', 'starting', 'ready', 'resetting', 'switching')
CASE_FIELDS = ('environment','case_id','rubrics','case_path','case_type','content_update')
REVIEW_METADATA_FIELDS = ('runtime_kind','source_case','description','description_i18n','target','related_objects','category','kind','trigger','effect','source_taxonomy','scene_id','scene_i18n','package_id','engine_version','taxonomy_mapping')

def case_fields(t):
    return {k:t[k] for k in REVIEW_METADATA_FIELDS if k in t and t.get('review_mode')=='informed_internal_review'} | ({'taxonomy':classify(t)} if classify(t) else {}) | ({'rubrics_i18n':t['rubrics_i18n']} if 'rubrics_i18n' in t else {}) | ({'content_update':t['content_update']} if t.get('content_update') else {}) | {'environment':t.get('environment',''), 'case_id':t.get('case_id',f"{t['id']}-R{t['revision']:02d}"), 'rubrics':t.get('rubrics',''), 'case_path':t.get('case_path','/?case='+t['id']), 'case_type':t.get('case_type','bug')}

class Problem(Exception):
    def __init__(self, status, message): self.status, self.message = status, message

class Store(BrowserSessions):
    problem_type=Problem
    case_fields=staticmethod(case_fields)
    def __init__(self, path, manifest, mode='mock', capacity=3, tokens=None, demo_token='local-demo', admin_token='', runner=None, build_sha='', ttl=180, max_age=3600):
        if mode not in ('mock', 'external'): raise ValueError('Invalid mode')
        if not 1 <= capacity <= 100: raise ValueError('Capacity must be 1..100')
        if mode == 'external' and (not isinstance(runner,list) or not runner or not all(isinstance(x,str) for x in runner) or not tokens or len(build_sha) != 64 or any(c not in '0123456789abcdef' for c in build_sha)):
            raise ValueError('External mode requires runner, per-reviewer tokens and exact build SHA256')
        self.mode,self.capacity,self.tokens,self.demo_token,self.admin_token,self.runner,self.build_sha,self.ttl,self.max_age=mode,capacity,tokens or {},demo_token,admin_token,runner,build_sha,ttl,max_age
        self.path=pathlib.Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.evidence_dir=self.path.parent/'evidence';self.evidence_dir.mkdir(exist_ok=True)
        self.stream_connections={};self.disconnect_deadlines={};self.runtime_health={};self.lock=threading.RLock();self.db=sqlite3.connect(self.path,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS logins(token_hash TEXT PRIMARY KEY, owner TEXT, reviewer TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,owner TEXT,reviewer TEXT,task_id TEXT,revision INTEGER,map TEXT,sha256 TEXT,build_sha256 TEXT,mode TEXT,status TEXT,slot INTEGER,created REAL,heartbeat REAL,stream_url TEXT,error TEXT);
        CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,session_id TEXT UNIQUE,owner TEXT,created REAL,payload TEXT);
        CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,session_id TEXT,owner TEXT,mime_type TEXT,sha256 TEXT,path TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,session_id TEXT,event TEXT,created REAL,detail TEXT);
        ''')
        columns={r[1] for r in self.db.execute('PRAGMA table_info(sessions)')}
        if 'case_metadata' not in columns:self.db.execute('ALTER TABLE sessions ADD COLUMN case_metadata TEXT')
        if 'runtime_id' not in columns:self.db.execute('ALTER TABLE sessions ADD COLUMN runtime_id TEXT')
        items=manifest['tasks'];self.tasks={x['id']:dict({k:v for k,v in x.items() if k!='taxonomy'},**case_fields(x)) for x in items}
        if len(self.tasks)!=len(items) or not items:raise ValueError('Invalid task manifest')
        import re
        for t in items:
            versions=t.get('review_compatible_versions',[])
            if not isinstance(versions,list) or any(not isinstance(v,dict) or type(v.get('revision'))!=int or v['revision']<1 or any(not isinstance(v.get(k),str) or not re.fullmatch(r'[0-9a-f]{64}',v[k]) for k in ('sha256','build_sha256')) for v in versions):raise ValueError('Invalid compatible review version')
            if is_browser(t):
                validate_browser_task(t)
                continue
            if not re.fullmatch(r'(?:U\d{3}|S(?:0[1-9]|1[0-9]|2[012])|H(?:0[1-9]|1[0-3]|15)|B0[1-3]|HB0[1-3]|AB0[1-3]|RB0[1-3]|R(?:0[1-9]|1[0-8])|A(?:0[1-9]|1[0-9]|2[0-5])|IB0[1-3]|I(?:0[1-9]|1[0-9]|2[01])|MVB0[1-2]|MV(?:0[1-9]|1[0-9]|2[0-2]))',t['id']) or not isinstance(t['revision'],int) or not re.fullmatch(r'[0-9a-f]{64}',t['sha256']):raise ValueError('Invalid task metadata')
            canonical=f"/Game/Auditor/Tasks/{t['id']}/R{t['revision']:02d}/TaskMap"
            migration=f"/Game/Auditor/Migration/UE561/{t['id']}/R{t['revision']:02d}/TaskMap_Candidate01"
            allowed=(canonical,migration,migration.removesuffix('01')+'02') if t['id'].startswith('U') else ()
            subway={'B01':'Concourse','B02':'Platform','B03':'Trackside'}
            indoor={'HB01':'LivingRoom','HB02':'KitchenDining','HB03':'BedroomSuite'}
            rural={'RB01':'RoadBend','RB02':'Roadside','RB03':'Canyon'}
            ancient={'AB01':'Market','AB02':'TeaHouse','AB03':'Courtyard'}
            industrial={'IB01':'AssemblyHall','IB02':'VehicleTest','IB03':'ControlRoom'}
            if t['id'] in industrial:allowed=('/Game/Auditor/Industrial/'+industrial[t['id']],)
            elif t['id'].startswith('I'):allowed=tuple('/Game/Auditor/Industrial/'+region+'?Task='+t['id'] for region in ('AssemblyHall','VehicleTest','ControlRoom'))
            elif t['id'] in rural:allowed=('/Game/Auditor/RuralAustralia/'+rural[t['id']],)
            elif t['id'].startswith('R'):allowed=tuple('/Game/Auditor/RuralAustralia/'+region+'?Task='+t['id'] for region in ('RoadBend','Roadside','Canyon'))
            elif t['id'] in ('MVB01','MVB02'):allowed=('/Game/Auditor/MedievalVillage/'+{'MVB01':'Market','MVB02':'Windmill'}[t['id']],)
            elif re.fullmatch(r'MV(?:0[1-9]|1[0-9]|2[0-2])',t['id']):allowed=tuple('/Game/Auditor/MedievalVillage/'+region+'?Task='+t['id'] for region in ('Market','Windmill'))
            elif t['id'] in ancient:allowed=('/Game/Auditor/AncientCity/'+ancient[t['id']],)
            elif t['id'].startswith('A'):allowed=tuple('/Game/Auditor/AncientCity/'+region+'?Task='+t['id'] for region in ('Market','TeaHouse','Courtyard'))
            elif t['id'] in subway:allowed=('/Game/Auditor/Subway/'+subway[t['id']],)
            elif t['id'] in indoor:allowed=('/Game/Auditor/Regions/'+indoor[t['id']],)
            elif t['id'].startswith('S'):allowed=tuple('/Game/Auditor/Subway/'+region+'?Task='+t['id'] for region in ('Concourse','Platform','Trackside'))
            elif t['id'].startswith('H'):allowed=tuple('/Game/Auditor/Regions/'+region+'?Task='+t['id'] for region in ('LivingRoom','KitchenDining','BedroomSuite'))
            if t['map'] not in allowed:raise ValueError('Invalid map')
            if 'build_sha256' in t and not re.fullmatch(r'[0-9a-f]{64}',t['build_sha256']):raise ValueError('Invalid task build hash')
            if 'rubrics_i18n' in t and any(not isinstance(t['rubrics_i18n'].get(lang,{}).get(key),str) or not t['rubrics_i18n'][lang][key].strip() for lang in ('zh','en') for key in ('expected','steps','criteria')):raise ValueError('Incomplete bilingual rubrics')
        self.migrate_review_history()
        existing_modes={r[0] for r in self.db.execute('SELECT DISTINCT mode FROM sessions')}
        if existing_modes and existing_modes!={mode}:raise ValueError('Use separate databases for mock and external modes')
        # Restart cannot release a GPU slot until stop is confirmed.
        with self.lock:
            self.db.execute("UPDATE sessions SET status=CASE WHEN slot IS NULL THEN 'closed' ELSE 'closing' END,error='Coordinator restarted; session ended' WHERE status IN ('queued','starting','ready','resetting','switching','closing')")
            self.db.commit()

    def migrate_review_history(self):
        """Backfill all available snapshots once, atomically; leave existing feedback untouched."""
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS review_history(id TEXT PRIMARY KEY,feedback_id TEXT NOT NULL,session_id TEXT NOT NULL,owner TEXT NOT NULL,created REAL NOT NULL,payload TEXT NOT NULL,source_key TEXT UNIQUE NOT NULL)')
            self.db.execute('CREATE INDEX IF NOT EXISTS review_history_owner ON review_history(owner,created)')
            self.db.execute('CREATE TABLE IF NOT EXISTS review_history_migrations(name TEXT PRIMARY KEY)')
            if self.db.execute("SELECT 1 FROM review_history_migrations WHERE name='initial-v1'").fetchone():return
            snapshots=[]
            for event in self.db.execute("SELECT id,detail FROM events WHERE event='feedback_updated' ORDER BY id"):
                detail=json.loads(event['detail']);fid=detail['feedback_id']
                row=self.db.execute('SELECT session_id,owner FROM feedback WHERE id=?',(fid,)).fetchone()
                if not row:raise ValueError('Cannot migrate review history: missing feedback for edit event')
                snapshots.append((detail['previous_created'],fid,row['session_id'],row['owner'],detail['previous_payload'],'event:'+str(event['id'])))
            for row in self.db.execute('SELECT * FROM feedback ORDER BY created,rowid'):
                snapshots.append((row['created'],row['id'],row['session_id'],row['owner'],json.loads(row['payload']),'initial:'+row['id']))
            for created,fid,sid,owner,payload,source in sorted(snapshots,key=lambda x:x[0]):
                self.append_review_history(fid,sid,owner,created,payload,source)
            self.db.execute("INSERT INTO review_history_migrations VALUES('initial-v1')")

    def append_review_history(self,fid,sid,owner,created,payload,source=None):
        hid=secrets.token_hex(16)
        self.db.execute('INSERT INTO review_history VALUES(?,?,?,?,?,?,?)',(hid,fid,sid,owner,created,json.dumps(payload,ensure_ascii=False),source or 'submission:'+hid))
        return hid

    def review_history(self,user=None):
        query='SELECT * FROM review_history';args=()
        if user is not None:query+=' WHERE owner=?';args=(user['owner'],)
        return [dict(json.loads(r['payload']),history_id=r['id'],feedback_id=r['feedback_id'],session_id=r['session_id'],reviewer_id=r['owner'],created=r['created']) for r in self.db.execute(query+' ORDER BY created,rowid',args)]

    def stream_connected(self,sid):
        with self.lock:
            self.stream_connections[sid]=self.stream_connections.get(sid,0)+1
            self.disconnect_deadlines.pop(sid,None)
            for row in self.db.execute('SELECT id FROM sessions WHERE COALESCE(runtime_id,id)=?',(sid,)):self.disconnect_deadlines.pop(row['id'],None)

    def stream_disconnected(self,sid):
        with self.lock:
            self.stream_connections[sid]=max(0,self.stream_connections.get(sid,0)-1)
            if not self.stream_connections[sid]:
                row=self.db.execute("SELECT id,status FROM sessions WHERE COALESCE(runtime_id,id)=? AND status IN ('ready','switching') ORDER BY created DESC LIMIT 1",(sid,)).fetchone()
                if row and row['status']=='ready':self.disconnect_deadlines[row['id']]=time.time()+10
                else:self.disconnect_deadlines.pop(sid,None)

    def event(self,sid,event,detail=''):
        self.db.execute('INSERT INTO events(session_id,event,created,detail) VALUES(?,?,?,?)',(sid,event,time.time(),detail))

    def login(self,token,reviewer):
        matched=None
        for secret,record in self.tokens.items():
            if hmac.compare_digest(str(token),secret):matched=record;break
        if matched:
            owner=str(matched['id']); reviewer=str(matched['reviewer'])
        elif self.mode=='mock' and not self.tokens and hmac.compare_digest(str(token),self.demo_token):
            owner=secrets.token_hex(16);reviewer=str(reviewer).strip()[:80]
        else:raise Problem(401,'访问令牌无效')
        if not reviewer:raise Problem(400,'请输入测试者姓名')
        cookie=secrets.token_urlsafe(32)
        with self.lock:
            self.db.execute('INSERT INTO logins VALUES(?,?,?,?)',(hashlib.sha256(cookie.encode()).hexdigest(),owner,reviewer,time.time()+43200));self.db.commit()
        return cookie,{'owner':owner,'reviewer':reviewer}

    def auth(self,cookie):
        with self.lock:
            row=self.db.execute('SELECT * FROM logins WHERE token_hash=? AND expires>?',(hashlib.sha256(cookie.encode()).hexdigest(),time.time())).fetchone()
            if not row:raise Problem(401,'请先登录')
            return dict(row)

    def auth_cookie_for_gateway(self,user):
        with self.lock:
            if not self.db.execute('SELECT 1 FROM logins WHERE token_hash=? AND expires>?',(user['token_hash'],time.time())).fetchone():raise Problem(401,'Login expired')

    def owned(self,sid,user):
        row=self.db.execute('SELECT * FROM sessions WHERE id=? AND owner=?',(sid,user['owner'])).fetchone()
        if not row:raise Problem(404,'会话不存在')
        return dict(row)

    def public(self,row):
        if not row:return None
        r=dict(row); q=0
        if r['status']=='queued':q=self.db.execute("SELECT count(*) FROM sessions WHERE status='queued' AND rowid<=(SELECT rowid FROM sessions WHERE id=?)",(r['id'],)).fetchone()[0]
        health=self.runtime_health.get(r['id'],{})
        if health.get('scheduler_waiting') and health.get('queue_position'):r['status']='queued'
        return ({'runtime_kind':'browser'} if self.browser_task(r) else {}) | {k:r[k] for k in ('id','task_id','revision','status','stream_url','error','mode')} | {'queue_position':self.runtime_health.get(r['id'],{}).get('queue_position') or q,'health':self.runtime_health.get(r['id'],{'checked_at':None,'game_running':None,'signalling_running':None,'streamer_registered':None})}

    def current(self,user):
        with self.lock:
            r=self.db.execute("SELECT * FROM sessions WHERE owner=? ORDER BY created DESC LIMIT 1",(user['owner'],)).fetchone()
            return self.public(r)

    def review_matches_task(self, vote, task):
        """Match an exact build or an explicitly verified unchanged-task version."""
        keys=('revision','sha256','build_sha256')
        version=tuple(vote.get(k) for k in keys)
        current=tuple(task.get(k,self.build_sha if k=='build_sha256' else None) for k in keys)
        return version==current or any(version==tuple(v.get(k) for k in keys) for v in task.get('review_compatible_versions',[]))

    def dashboard(self,user):
        """Latest applicable votes per stable identity; baseline checks are separate."""
        with self.lock:
            latest={}
            for row in self.db.execute('SELECT f.owner,f.payload FROM feedback f ORDER BY f.created,f.rowid'):
                vote=json.loads(row['payload']);task=self.tasks.get(vote.get('task_id'))
                if not task or vote.get('mode')!=self.mode:continue
                if not self.review_matches_task(vote,task):continue
                if vote.get('quality') not in ('pass','fail','uncertain'):continue
                latest[(task['id'],row['owner'])]=vote
            # Re-review queue: latest submission per person/task across versions.
            # Keep acceptance votes above restricted to applicable versions.
            latest_submissions={}
            for row in self.db.execute('SELECT owner,created,payload FROM review_history ORDER BY created,rowid'):
                vote=json.loads(row['payload']);task=self.tasks.get(vote.get('task_id'))
                if not task or vote.get('mode')!=self.mode or vote.get('quality') not in ('pass','fail','uncertain'):continue
                latest_submissions[(task['id'],row['owner'])]=(vote,row['created'])
            # Public stable selectors contain no login credentials or internal owner values.
            reviewer_key=lambda owner: hashlib.sha256(('progress-reviewer:'+owner).encode()).hexdigest()
            names={owner:v.get('reviewer','Reviewer') for (_,owner),(v,_) in latest_submissions.items()}
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='participants'").fetchone():
                names.update({r['id']:r['name'] for r in self.db.execute('SELECT id,name FROM participants')})
            names[user['owner']]=user['reviewer']
            reviewer_options=[{'id':reviewer_key(owner),'name':name,'mine':owner==user['owner']} for owner,name in names.items()]
            reviewer_options.sort(key=lambda r:(not r['mine'],r['name'].casefold(),r['id']))
            total_reviews={}
            for row in self.db.execute('SELECT owner,payload FROM review_history'):
                review=json.loads(row['payload']);tid=review.get('task_id')
                if tid in self.tasks and review.get('mode')==self.mode and review.get('quality') in ('pass','fail','uncertain'):
                    total_reviews.setdefault(tid,set()).add((row['owner'],review.get('revision'),review.get('sha256'),review.get('build_sha256')))
            progress=[]
            for task in self.tasks.values():
                votes=[v for (tid,owner),v in latest.items() if tid==task['id']]
                approvals=[v['reviewer'] for v in votes if v['quality']=='pass']
                progress.append({'id':task['id'],'family':task.get('family','urban'),'scene':task.get('scene_id') or task['map'].split('?')[0].rsplit('/',1)[-1],
                    'content_update':task.get('content_update'),'case_type':task['case_type'],'taxonomy':task.get('taxonomy',{}),'approvals':len(approvals),'reviewers':approvals,'reviews':len(votes),'total_reviews':len(total_reviews.get(task['id'],())),
                    'reviewer_results':[{'id':reviewer_key(owner),'quality':v['quality']} for (tid,owner),v in latest.items() if tid==task['id']],
                    'latest_reviewer_results':[{'id':reviewer_key(owner),'quality':v['quality'],'updated_at':created,
                        'current_version':all(v.get(k)==task.get(k,self.build_sha if k=='build_sha256' else None) for k in ('revision','sha256','build_sha256')),
                        'counts_toward_current':self.review_matches_task(v,task)} for (tid,owner),(v,created) in latest_submissions.items() if tid==task['id']],
                    'accepted':len(approvals)>=2,'my_quality':latest.get((task['id'],user['owner']),{}).get('quality')})
            rows=[dict(row) for row in self.db.execute("SELECT id,owner,reviewer,task_id,status,slot,created FROM sessions WHERE status IN ('queued','starting','ready','resetting','switching','closing') ORDER BY created,rowid")]
            running=[];queue=[]
            for row in rows:
                public={k:row[k] for k in ('reviewer','task_id','status','created')};public['mine']=row['owner']==user['owner']
                health=self.runtime_health.get(row['id'],{})
                if health.get('scheduler_waiting') and health.get('queue_position'):
                    public.update(status='queued',position=health['queue_position']);queue.append(public)
                elif row['slot'] is not None:
                    public['slot']=(health.get('physical_slot') if health.get('physical_slot') is not None else row['slot'])+1;running.append(public)
                elif row['status']=='queued':public['position']=len(queue)+1;queue.append(public)
            bugs=[t for t in progress if t['case_type']!='baseline']
            return {'capacity':self.capacity,'running':running,'queue':queue,'tasks':progress,'reviewer_options':reviewer_options,'taxonomy':summarize(progress),'updated_at':time.time(),
                'counts':{'environments':len({t.get('family','urban') for t in self.tasks.values()}),
                    'scenes':len({(t.get('family','urban'),t.get('scene_id') or t['map'].split('?')[0]) for t in self.tasks.values()}),
                    'tasks':len(bugs),'baselines':len(progress)-len(bugs),'accepted':sum(t['accepted'] for t in bugs)}}

    def reviews(self,user):
        """Return this reviewer's latest applicable review of each task."""
        with self.lock:
            result={}
            for row in self.db.execute('SELECT id,created,payload FROM feedback WHERE owner=? ORDER BY created,rowid',(user['owner'],)):
                v=json.loads(row['payload']);t=self.tasks.get(v.get('task_id'))
                if not t or v.get('mode')!=self.mode or v.get('quality') not in ('pass','fail','uncertain'):continue
                if not self.review_matches_task(v,t):continue
                result[t['id']]={k:v.get(k) for k in ('task_id','session_id','difficulty','quality','comment','prior_exposure','evidence_ids')}
                result[t['id']].update(feedback_id=row['id'],updated_at=row['created'])
            return result

    def task_reviews(self,task_id,user):
        """Read-only peer reviews; retain the latest entry per reviewer and task version."""
        with self.lock:
            task=self.tasks.get(task_id)
            if not task:raise Problem(404,'Task not found')
            latest={};latest_applicable={}
            rows=self.db.execute('SELECT f.owner,f.created,f.payload FROM feedback f JOIN sessions s ON s.id=f.session_id WHERE s.task_id=? AND f.owner<>? ORDER BY f.created,f.rowid',(task_id,user['owner']))
            for row in rows:
                v=json.loads(row['payload'])
                if v.get('task_id')!=task_id or v.get('mode')!=self.mode or v.get('quality') not in ('pass','fail','uncertain'):continue
                version=tuple(v.get(k) for k in ('revision','sha256','build_sha256'))
                current=all(v.get(k)==task.get(k,self.build_sha if k=='build_sha256' else None) for k in ('revision','sha256','build_sha256'))
                if self.review_matches_task(v,task):latest_applicable[row['owner']]=version
                latest[(row['owner'],version)]={'reviewer':v.get('reviewer','Reviewer'),'difficulty':v.get('difficulty'),'quality':v['quality'],'comment':v.get('comment',''),'updated_at':row['created'],'current_version':current,'counts_toward_current':self.review_matches_task(v,task)}
            for (owner,version),entry in latest.items():entry['counts_toward_current']=entry['counts_toward_current'] and latest_applicable.get(owner)==version
            return sorted(latest.values(),key=lambda r:(not r['current_version'],-r['updated_at'],r['reviewer']))

    def update_review(self,fid,user,data):
        with self.lock:
            row=self.db.execute('SELECT * FROM feedback WHERE id=? AND owner=?',(fid,user['owner'])).fetchone()
            if not row:raise Problem(404,'Review not found')
            old=json.loads(row['payload']);latest=self.reviews(user).get(old['task_id'])
            if not latest or latest['feedback_id']!=fid:raise Problem(409,'This review has been superseded. Reload the page before editing.')
            if data.get('updated_at')!=row['created']:raise Problem(409,'Your review changed in another window. Reload the page before editing.')
            difficulty=data.get('difficulty');quality=data.get('quality');comment=data.get('comment','')
            if type(difficulty)!=int or not 1<=difficulty<=5:raise Problem(400,'Difficulty must be an integer from 1 to 5')
            if quality not in ('pass','fail','uncertain'):raise Problem(400,'Invalid quality')
            if not isinstance(comment,str) or len(comment)>10000:raise Problem(400,'Comment is too long')
            session=self.owned(old['session_id'],user)
            if quality!='uncertain' and session['status']!='ready' and not self.db.execute("SELECT 1 FROM events WHERE session_id=? AND event='runtime_ready'",(session['id'],)).fetchone():raise Problem(409,'Run this task before submitting Pass or Fail')
            ids=data.get('evidence_ids',old.get('evidence_ids',[]))
            if not isinstance(ids,list) or len(ids)>5:raise Problem(400,'At most 5 attachments')
            for eid in ids:
                if not self.db.execute('SELECT 1 FROM evidence WHERE id=? AND owner=? AND session_id=?',(eid,user['owner'],session['id'])).fetchone():raise Problem(400,'Attachment does not belong to this review')
            new=old|dict(difficulty=difficulty,quality=quality,comment=comment.strip(),prior_exposure=data.get('prior_exposure') is True,evidence_ids=ids)
            # Keep the previous complete snapshot in the audit log before replacing the current vote.
            now=time.time()
            with self.db:
                self.event(session['id'],'feedback_updated',json.dumps({'feedback_id':fid,'previous_created':row['created'],'previous_payload':old},ensure_ascii=False))
                self.append_review_history(fid,session['id'],user['owner'],now,new)
                self.db.execute('UPDATE feedback SET created=?,payload=? WHERE id=?',(now,json.dumps(new,ensure_ascii=False),fid))
            return self.reviews(user)[old['task_id']]

    def create(self,user,task_id=None):
        with self.lock:
            old=self.db.execute("SELECT * FROM sessions WHERE owner=? AND status IN ('queued','starting','ready','resetting','switching','closing') LIMIT 1",(user['owner'],)).fetchone()
            if old:return self.public(old)
            if task_id and task_id not in self.tasks:raise Problem(400,'任务不存在')
            if not task_id:
                done={r[0] for r in self.db.execute('SELECT s.task_id FROM sessions s JOIN feedback f ON s.id=f.session_id WHERE s.owner=? AND s.mode=?',(user['owner'],self.mode))}
                choices=[k for k in self.tasks if k not in done] or list(self.tasks)
                def load(k):return self.db.execute("SELECT count(*) FROM sessions s WHERE s.task_id=? AND s.mode=? AND (s.status IN ('queued','starting','ready','resetting','switching') OR EXISTS(SELECT 1 FROM feedback f WHERE f.session_id=s.id))",(k,self.mode)).fetchone()[0]
                task_id=min(choices,key=load)
            t=self.tasks[task_id];sid=secrets.token_hex(16);now=time.time()
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(sid,user['owner'],user['reviewer'],t['id'],t['revision'],t['map'],t['sha256'],t.get('build_sha256',self.build_sha),self.mode,'queued',None,now,now,None,None,json.dumps(case_fields(t),ensure_ascii=False),sid));self.event(sid,'created')
            if is_browser(t):self.prepare_browser(sid,t)
            self.db.commit()
            return self.public(self.owned(sid,user))

    def stream_session(self,runtime_id,user):
        with self.lock:
            row=self.db.execute("SELECT * FROM sessions WHERE owner=? AND COALESCE(runtime_id,id)=? AND status IN ('ready','switching') ORDER BY created DESC LIMIT 1",(user['owner'],runtime_id)).fetchone()
            if not row:raise Problem(404,'Stream not active')
            return dict(row)

    def switch_task(self,sid,user,task_id):
        with self.lock:
            old=self.owned(sid,user);target=self.tasks.get(task_id)
            if not target:raise Problem(400,'Task not found')
            if old['status']!='ready':raise Problem(409,'Wait for the current task to be ready')
            if old['task_id']==task_id:return self.public(old)
            source=self.tasks[old['task_id']]
            if is_browser(source) and is_browser(target):return self.switch_browser(old,user,target)
            if not source.get('runtime_switch') or not target.get('runtime_switch') or source.get('family')!=target.get('family') or old['build_sha256']!=target.get('build_sha256',self.build_sha):raise Problem(409,'These tasks require different runtime instances')
            if old['slot'] is None:raise Problem(409,'No runtime slot to reuse')
            # One logical session per task keeps every feedback/evidence snapshot
            # attached to its original task; the runtime and slot stay with the owner.
            new_id=secrets.token_hex(16);now=time.time();runtime_id=old.get('runtime_id') or sid
            self.db.execute("UPDATE sessions SET status='closed',slot=NULL,stream_url=NULL WHERE id=?",(sid,))
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(new_id,user['owner'],user['reviewer'],target['id'],target['revision'],target['map'],target['sha256'],target.get('build_sha256',self.build_sha),self.mode,'switching',old['slot'],now,now,old['stream_url'],None,json.dumps(case_fields(target),ensure_ascii=False),runtime_id))
            self.disconnect_deadlines.pop(sid,None)
            self.event(sid,'task_switched',new_id);self.event(new_id,'switching',sid);self.db.commit()
            return self.public(self.owned(new_id,user))

    def change(self,sid,user,op):
        with self.lock:
            s=self.owned(sid,user)
            if op=='heartbeat':
                if s['status'] not in ACTIVE:raise Problem(409,'会话已结束')
                self.db.execute('UPDATE sessions SET heartbeat=? WHERE id=?',(time.time(),sid))
            elif op=='close':
                state='closing' if s['slot'] is not None else 'closed'
                if s['status'] not in ('closed','failed'):self.db.execute('UPDATE sessions SET status=?,stream_url=NULL WHERE id=?',(state,sid));self.event(sid,'close_requested')
            elif op in ('reset','restart'):
                if self.db.execute('SELECT 1 FROM feedback WHERE session_id=?',(sid,)).fetchone():raise Problem(409,'已有已保存反馈，请开始新会话')
                if op=='restart' and s['status'] in ('closed','failed'):return self.create(user,s['task_id'])
                if s['status'] not in ('ready','starting'):raise Problem(409,'请等待当前启动或清理完成')
                if self.browser_task(s):self.prepare_browser(sid,self.tasks[s['task_id']])
                else:self.db.execute("UPDATE sessions SET status='resetting',stream_url=NULL,error=NULL WHERE id=?",(sid,))
                self.event(sid,'reset_requested')
            self.db.commit();return self.public(self.owned(sid,user))

    def feedback(self,sid,user,data):
        with self.lock:
            s=self.owned(sid,user)
            if s['status'] not in ('ready','failed','closing','closed'):raise Problem(409,'等待会话就绪后提交反馈')
            prior=self.db.execute('SELECT id FROM feedback WHERE session_id=?',(sid,)).fetchone()
            if prior:return prior[0]
            if any(k in data for k in ('difficulty','quality','comment')):
                difficulty=data.get('difficulty');quality=data.get('quality');comment=data.get('comment','')
                if type(difficulty)!=int or not 1<=difficulty<=5:raise Problem(400,'Difficulty须为1–5的整数')
                if quality not in ('pass','fail','uncertain'):raise Problem(400,'Quality须为pass/fail/uncertain')
                if not isinstance(comment,str) or len(comment)>10000:raise Problem(400,'Comment最多10000字')
                if s['status']!='ready' and quality!='uncertain' and not self.db.execute("SELECT 1 FROM events WHERE session_id=? AND event='runtime_ready'",(sid,)).fetchone():raise Problem(409,'尚未成功启动过游戏，请选择uncertain或先启动游戏；填写内容会保留')
                fields={'difficulty':difficulty,'quality':quality,'comment':comment.strip(),'feedback_format':'case_review_v2','review_protocol':'guided_case_review'}
            else:
                # Old clients/records remain observations; never infer quality from verdict.
                v=data.get('verdict');c=data.get('confidence')
                if v not in VERDICTS or type(c)!=int or not 1<=c<=5:raise Problem(400,'判定或置信度无效')
                fields={k:str(data.get(k,'')).strip() for k in ('description','location','steps')}
                if not fields['description'] or any(len(x)>10000 for x in fields.values()):raise Problem(400,'请输入描述（每项最多10000字）')
                if s['status']!='ready' and v!='technical_issue':raise Problem(409,'未就绪或已结束的会话只能报告技术问题')
                fields.update(verdict=v,confidence=c,feedback_format='legacy_observation')
            ids=data.get('evidence_ids',[])
            if not isinstance(ids,list) or len(ids)>5:raise Problem(400,'最多5张截图')
            for eid in ids:
                if not self.db.execute('SELECT 1 FROM evidence WHERE id=? AND owner=? AND session_id=?',(eid,user['owner'],sid)).fetchone():raise Problem(400,'证据不属于该会话')
            payload={k:s[k] for k in ('task_id','revision','sha256','build_sha256','mode','reviewer')}
            snapshot=json.loads(s['case_metadata']) if s.get('case_metadata') else case_fields({'id':s['task_id'],'revision':s['revision']})
            payload.update(snapshot);payload.update(fields);payload.update(reviewer_id=s['owner'],prior_exposure=data.get('prior_exposure') is True,evidence_ids=ids,status='observation_submitted',session_id=sid)
            fid=secrets.token_hex(16);now=time.time()
            with self.db:
                self.db.execute('INSERT INTO feedback VALUES(?,?,?,?,?)',(fid,sid,user['owner'],now,json.dumps(payload,ensure_ascii=False)))
                self.append_review_history(fid,sid,user['owner'],now,payload)
                self.event(sid,'feedback_submitted',fid)
            return fid

    def evidence(self,sid,user,data):
        with self.lock:
            s=self.owned(sid,user)
            if s['status'] not in ACTIVE+('closed','failed'):raise Problem(409,'会话尚在清理')
            if self.db.execute('SELECT count(*) FROM evidence WHERE session_id=?',(sid,)).fetchone()[0]>=5:raise Problem(400,'最多5张截图')
            try:raw=base64.b64decode(data.get('content_base64',''),validate=True)
            except Exception:raise Problem(400,'截图编码无效')
            mime=data.get('mime_type');valid=(mime=='image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/jpeg' and raw.startswith(b'\xff\xd8\xff'))
            if not valid or len(raw)>5*1024*1024:raise Problem(400,'仅支持5MiB以内PNG/JPEG截图')
            eid=secrets.token_hex(16);path=self.evidence_dir/eid;path.write_bytes(raw)
            self.db.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?)',(eid,sid,user['owner'],mime,hashlib.sha256(raw).hexdigest(),str(path),time.time()));self.db.commit();return eid

    def call_runner(self,op,s):
        if self.mode!='mock' and os.getenv('REVIEW_SHARED_SCHEDULER'):
            if not hasattr(self,'shared_runtime'):
                from shared_runtime import SharedRuntime
                self.shared_runtime=SharedRuntime(self,os.environ['REVIEW_SHARED_SCHEDULER'])
            return self.shared_runtime.call(op,s)
        if self.mode=='mock':return {'ready':op!='stop','stopped':op=='stop','stream_url':None}
        cmd=self.runner+[op,s.get('runtime_id') or s['id'],s['map'],str(s['slot'])]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=15,check=True)
        r=json.loads(p.stdout)
        if not isinstance(r,dict):raise ValueError('Invalid runner response')
        return r

    def tick(self):
        # One coordinator thread. Never release a slot if cleanup fails.
        with self.lock:
            now=time.time()
            for sid,deadline in list(self.disconnect_deadlines.items()):
                if now>=deadline:
                    self.db.execute("UPDATE sessions SET status=CASE WHEN slot IS NULL THEN 'closed' ELSE 'closing' END,stream_url=NULL,error='Browser disconnected' WHERE id=? AND status IN ('starting','ready','switching')",(sid,))
                    self.disconnect_deadlines.pop(sid,None)
            self.db.execute("UPDATE sessions SET status=CASE WHEN slot IS NULL THEN 'closed' ELSE 'closing' END,stream_url=NULL,error='Session expired' WHERE status IN ('queued','starting','ready','resetting','switching') AND (heartbeat<? OR created<?)",(now-self.ttl,now-self.max_age))
            work=[dict(r) for r in self.db.execute("SELECT * FROM sessions WHERE status IN ('closing','resetting','starting','ready','switching')")];self.db.commit()
        for s in work:
            if self.browser_task(s):
                self.tick_browser(s,now)
                continue
            try:
                if s['status'] in ('closing','resetting'):
                    result=self.call_runner('stop',s)
                    if result.get('stopped') is not True:raise RuntimeError('Stop not confirmed')
                    with self.lock:
                        self.runtime_health[s['id']]={'checked_at':time.time(),'game_running':False,'signalling_running':False,'streamer_registered':False}
                        current=dict(self.db.execute('SELECT * FROM sessions WHERE id=?',(s['id'],)).fetchone())
                        state='queued' if s['status']=='resetting' and current['status']=='resetting' else 'closed'
                        self.db.execute('UPDATE sessions SET status=?,slot=NULL,stream_url=NULL WHERE id=?',(state,s['id']));self.event(s['id'],state);self.db.commit()
                else:
                    result=self.call_runner('switch' if s['status']=='switching' else 'status',s)
                    with self.lock:
                        self.runtime_health[s['id']]={'checked_at':time.time(),**{key:result.get(key) if type(result.get(key)) is bool else None for key in ('game_running','signalling_running','streamer_registered','scheduler_waiting')},'queue_position':result.get('queue_position'),'physical_slot':result.get('physical_slot')}
                        if result.get('ready'):
                            if s['status'] in ('starting','switching'):self.event(s['id'],'runtime_ready')
                            runtime_id=s.get('runtime_id') or s['id']
                            url=None if self.mode=='mock' else '/stream/'+runtime_id+'/'
                            if url and os.getenv('REVIEW_STREAM_PORTS'):
                                from urllib.parse import urlencode
                                origin=os.environ['REVIEW_PUBLIC_ORIGIN'];ws=origin.replace('https://','wss://').replace('http://','ws://')
                                url+='?'+urlencode({'ss':ws+'/stream/'+runtime_id+'/ws','AutoConnect':'true','AutoPlayVideo':'true','StartVideoMuted':'true','HoveringMouse':'false','HideUI':'true',**({'ForceTURN':'true'} if os.getenv('REVIEW_FORCE_TURN')=='1' else {})})
                            self.db.execute("UPDATE sessions SET status='ready',stream_url=?,error=NULL WHERE id=? AND status IN ('starting','ready','switching')",(url,s['id']))
                        elif not result.get('scheduler_waiting') and (result.get('game_running') is False or result.get('signalling_running') is False or s['status']=='ready' or now-(self.db.execute("SELECT MAX(created) FROM events WHERE session_id=? AND event IN ('starting','switching')",(s['id'],)).fetchone()[0] or s['created'])>120):
                            reason=result.get('error')
                            error=reason if reason in ('Runtime process exited','Streamer readiness probe failed','Streamer disconnected') else 'Runtime unavailable'
                            self.event(s['id'],'runtime_unavailable',error)
                            self.db.execute("UPDATE sessions SET status='closing',stream_url=NULL,error=? WHERE id=? AND status IN ('starting','ready','switching')",(error,s['id']))
                        self.db.commit()
            except Exception:
                with self.lock:
                    self.db.execute("UPDATE sessions SET status='closing',stream_url=NULL,error='Runtime adapter failed; slot quarantined until cleanup succeeds' WHERE id=? AND status!='closed'",(s['id'],));self.db.commit()
        with self.lock:
            used={r[0] for r in self.db.execute('SELECT slot FROM sessions WHERE slot IS NOT NULL')}
            # Shared mode registers every waiter centrally; these are logical handles, not GPU slots.
            count=self.db.execute("SELECT count(*) FROM sessions WHERE status='queued'").fetchone()[0]
            limit=(max(used,default=-1)+1+count) if os.getenv('REVIEW_SHARED_SCHEDULER') else self.capacity
            free=[i for i in range(limit) if i not in used]
            queued=[dict(r) for r in self.db.execute("SELECT * FROM sessions WHERE status='queued' ORDER BY rowid LIMIT ?",(len(free),))]
            for s,slot in zip(queued,free):
                s['slot']=slot;self.db.execute("UPDATE sessions SET status='starting',slot=? WHERE id=?",(slot,s['id']));self.event(s['id'],'starting')
            self.db.commit()
        for s in queued:
            try:self.call_runner('start',s)
            except Exception:
                with self.lock:self.db.execute("UPDATE sessions SET status='closing',error='Runtime launch failed' WHERE id=? AND status!='closed'",(s['id'],));self.db.commit()

class Handler(BaseHTTPRequestHandler):
    server_version='BugReview/1'
    def log_message(self,fmt,*args):pass # do not log credentials or evidence URLs
    @property
    def store(self):return self.server.store
    def reply(self,status,data,headers=None,raw=False):
        body=data if raw else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8' if not raw else headers.pop('Content-Type','application/octet-stream'))
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'self'; frame-src 'self'; connect-src 'self'; img-src 'self' blob: data:; object-src 'none'; frame-ancestors 'self'")
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def user(self):
        c=http.cookies.SimpleCookie()
        try:c.load(self.headers.get('Cookie',''))
        except http.cookies.CookieError:raise Problem(401,'请先登录')
        name=getattr(self.server,'cookie_name','review_session')
        return self.store.auth(c[name].value if name in c else '')
    def data(self):
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise Problem(415,'使用application/json')
        n=int(self.headers.get('Content-Length','0'))
        if not 0<n<8*1024*1024:raise Problem(413,'请求过大或为空')
        d=json.loads(self.rfile.read(n))
        if not isinstance(d,dict):raise Problem(400,'JSON对象必填')
        return d
    def do_GET(self):self.handle_api('GET')
    def do_POST(self):self.handle_api('POST')
    def handle_api(self,method):
        try:
            path=urlparse(self.path).path;s=self.store
            if method=='GET' and path.startswith('/local-open/'):
                ticket_file=os.getenv('REVIEW_LOCAL_TICKET_FILE')
                if not ticket_file or self.client_address[0]!='127.0.0.1':raise Problem(404,'接口不存在')
                code=path.rsplit('/',1)[-1]
                with s.lock:
                    ticket_path=pathlib.Path(ticket_file)
                    if not ticket_path.exists():raise Problem(410,'本机登录链接已失效')
                    ticket=json.loads(ticket_path.read_text())
                    if ticket['expires']<time.time() or not hmac.compare_digest(hashlib.sha256(code.encode()).hexdigest(),ticket['code_hash']):raise Problem(403,'本机登录链接无效')
                    ticket_path.unlink()
                    cookie,_=s.login(ticket['token'],'本机评审')
                secure='; Secure' if self.server.public_origin.startswith('https://') else ''
                return self.reply(303,{}, {'Location':'/?case=U018','Set-Cookie':f'{self.server.cookie_name}={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}'})
            if method=='GET' and path.startswith('/stream/'):
                from stream_gateway import proxy
                return proxy(self)
            if method=='GET' and path in ('/','/index.html','/app.js','/style.css','/review-bridge.js','/medieval-prop-attributions.md','/ancient-prop-attributions.md'):
                name='index.html' if path=='/' else path[1:];mime={'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','md':'text/plain; charset=utf-8'}[name.split('.')[-1]]
                return self.reply(200,(BASE/'static'/name).read_bytes(),{'Content-Type':mime},True)
            if method=='GET' and path=='/health':return self.reply(200,{'ok':True,'mode':s.mode})
            if method=='GET' and path=='/api/entry':
                entry=getattr(self.server,'participants',None)
                return self.reply(200,{'mode':entry.mode if entry else 'token','reviewers':[{'name':r['name']} for r in entry.roster] if entry else []})
            if method=='POST':
                origin=self.headers.get('Origin')
                if origin!=self.server.public_origin:raise Problem(403,'来源不匹配')
                d=self.data()
                if path in ('/api/participants','/api/participant-login'):
                    entry=getattr(self.server,'participants',None)
                    if not entry:raise Problem(404,'姓名登录未启用')
                    try:
                        if path=='/api/participants':return self.reply(200,{'reviewers':entry.options(d.get('access_code','')),'allow_new_names':entry.allow_new})
                        cookie,user=entry.login(d.get('access_code',''),d.get('reviewer',''))
                    except PermissionError as e:raise Problem(401,str(e))
                    except ValueError as e:raise Problem(400,str(e))
                    secure='; Secure' if self.server.public_origin.startswith('https://') else ''
                    return self.reply(200,{'reviewer':user['reviewer'],'owner':user['owner']},{'Set-Cookie':f'{self.server.cookie_name}={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}'})
                if path=='/api/local-login':
                    owner=getattr(self.server,'local_autologin_owner','')
                    if not owner or self.client_address[0]!='127.0.0.1' or urlparse(self.server.public_origin).hostname not in ('127.0.0.1','localhost'):raise Problem(404,'接口不存在')
                    token=next((token for token,record in s.tokens.items() if record['id']==owner),None)
                    if not token:raise Problem(503,'本机身份未配置')
                    cookie,user=s.login(token,'')
                    return self.reply(200,{'reviewer':user['reviewer'],'local':True},{'Set-Cookie':f'{self.server.cookie_name}={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'})
                if path=='/api/login':
                    cookie,user=s.login(d.get('token',''),d.get('reviewer',''))
                    secure='; Secure' if self.server.public_origin.startswith('https://') else ''
                    return self.reply(200,{'reviewer':user['reviewer']},{'Set-Cookie':f'{self.server.cookie_name}={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}'})
            if path.startswith('/api/admin/') and method=='GET':
                given=self.headers.get('Authorization','').removeprefix('Bearer ')
                if not s.admin_token or not hmac.compare_digest(given,s.admin_token):raise Problem(403,'需要管理员令牌')
                if path.startswith('/api/admin/evidence/'):
                    with s.lock:r=s.db.execute('SELECT * FROM evidence WHERE id=?',(path.rsplit('/',1)[1],)).fetchone()
                    if not r:raise Problem(404,'证据不存在')
                    return self.reply(200,pathlib.Path(r['path']).read_bytes(),{'Content-Type':r['mime_type']},True)
                if path!='/api/admin/export':raise Problem(404,'接口不存在')
                with s.lock:
                    rows=[dict(r) for r in s.db.execute('SELECT f.id,f.owner,f.created,f.payload FROM feedback f ORDER BY f.created')]
                    history=s.review_history()
                    attachments=[{k:r[k] for k in ('id','session_id','mime_type','sha256','created')} for r in s.db.execute('SELECT * FROM evidence')]
                return self.reply(200,{'review_history':history,'feedback':[dict({'reviewer_id':r['owner']},id=r['id'],created=r['created'],**json.loads(r['payload'])) for r in rows], 'evidence':attachments,'tasks':[{k:t[k] for k in ('id','revision','sha256','runtime_switch','runtime_kind','source_case')+CASE_FIELDS+(REVIEW_METADATA_FIELDS if t.get('review_mode')=='informed_internal_review' else ())+('build_sha256','taxonomy')+(('rubrics_i18n','family','title','subcategory','taxonomy_label') if 'rubrics_i18n' in t else ()) if k in t} for t in s.tasks.values()],'mode':s.mode,'build_sha256':s.build_sha})
            user=self.user()
            if method=='GET':
                if path=='/api/me':return self.reply(200,{'reviewer':user['reviewer'],'mode':s.mode,'local':bool(getattr(self.server,'local_autologin_owner',''))})
                if path=='/api/reviews/history':
                    with s.lock:history=s.review_history(user)
                    return self.reply(200,{'review_history':history})
                if path=='/api/reviews':return self.reply(200,{'reviews':s.reviews(user)})
                if path.startswith('/api/tasks/') and path.endswith('/reviews') and len(path.split('/'))==5:return self.reply(200,{'reviews':s.task_reviews(path.split('/')[3],user)})
                if path=='/api/dashboard':return self.reply(200,s.dashboard(user))
                if path=='/api/tasks':return self.reply(200,{'tasks':[{k:t[k] for k in ('id','revision','sha256','runtime_switch','runtime_kind','source_case')+CASE_FIELDS+(REVIEW_METADATA_FIELDS if t.get('review_mode')=='informed_internal_review' else ())+('build_sha256','taxonomy')+(('rubrics_i18n','family','title','subcategory','taxonomy_label') if 'rubrics_i18n' in t else ()) if k in t} for t in s.tasks.values()],'mode':s.mode})
                if path=='/api/sessions/current':return self.reply(200,{'session':s.current(user)})
                if path=='/api/stream-authorize':
                    sid=parse_qs(urlparse(self.path).query).get('session_id',[''])[0]
                    with s.lock:r=s.stream_session(sid,user)
                    if r['status'] not in ('ready','switching') or r['mode']!='external' or r['slot'] is None:raise Problem(403,'流尚未就绪')
                    slot=r['slot']
                    if hasattr(s,'shared_runtime'):slot=s.shared_runtime.port(r)-s.shared_runtime.c['player_port']
                    return self.reply(200,{'authorized':True},{'X-Review-Slot':str(slot)})
                if path.startswith('/api/evidence/'):
                    with s.lock:r=s.db.execute('SELECT * FROM evidence WHERE id=? AND owner=?',(path.rsplit('/',1)[1],user['owner'])).fetchone()
                    if not r:raise Problem(404,'证据不存在')
                    return self.reply(200,pathlib.Path(r['path']).read_bytes(),{'Content-Type':r['mime_type']},True)
            else:
                if path=='/api/logout':
                    with s.lock:
                        s.db.execute("UPDATE sessions SET status=CASE WHEN slot IS NULL THEN 'closed' ELSE 'closing' END,stream_url=NULL WHERE owner=? AND status IN ('queued','starting','ready','resetting','switching')",(user['owner'],))
                        s.db.execute('DELETE FROM logins WHERE token_hash=?',(user['token_hash'],));s.db.commit()
                    return self.reply(200,{'ok':True},{'Set-Cookie':self.server.cookie_name+'=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict'})
                if path=='/api/sessions':return self.reply(200,{'session':s.create(user,d.get('task_id'))})
                parts=path.strip('/').split('/')
                if len(parts)==3 and parts[:2]==['api','reviews']:return self.reply(200,{'review':s.update_review(parts[2],user,d)})
                if len(parts)==4 and parts[:2]==['api','sessions']:
                    sid,op=parts[2:]
                    if op in ('heartbeat','reset','restart','close'):return self.reply(200,{'session':s.change(sid,user,op)})
                    if op in ('browser-ready','browser-failed'):return self.reply(200,{'session':s.browser_report(sid,user,d,failed=op=='browser-failed')})
                    if op=='switch':return self.reply(200,{'session':s.switch_task(sid,user,d.get('task_id'))})
                    if op=='feedback':return self.reply(200,{'feedback_id':s.feedback(sid,user,d)})
                    if op=='evidence':return self.reply(200,{'evidence_id':s.evidence(sid,user,d)})
            raise Problem(404,'接口不存在')
        except Problem as e:self.reply(e.status,{'error':e.message})
        except (ValueError,TypeError,KeyError):self.reply(400,{'error':'请求格式无效'})
        except Exception:self.reply(500,{'error':'服务内部错误'})

def make_server(store,host='127.0.0.1',port=8090,origin=None):
    server=ThreadingHTTPServer((host,port),Handler);server.store=store;server.public_origin=origin or f'http://{host}:{server.server_port}';server.stream_ports=[];server.cookie_name='review_session';return server

def main():
    mode=os.getenv('REVIEW_MODE','mock');host=os.getenv('REVIEW_HOST','127.0.0.1');port=int(os.getenv('REVIEW_PORT','8090'))
    token=os.getenv('REVIEW_DEMO_TOKEN','local-demo')
    if host not in ('127.0.0.1','localhost') and token=='local-demo' and mode=='mock':raise SystemExit('Set a non-default REVIEW_DEMO_TOKEN before exposing mock mode')
    manifest=json.loads(pathlib.Path(os.getenv('REVIEW_MANIFEST',str(BASE/'tasks.json'))).read_text())
    store=Store(os.getenv('REVIEW_DB',str(BASE/'var/review.sqlite3')),manifest,mode,int(os.getenv('REVIEW_CAPACITY','3')),json.loads(os.getenv('REVIEW_TOKENS_JSON','{}')),token,os.getenv('REVIEW_ADMIN_TOKEN',''),json.loads(os.getenv('REVIEW_RUNNER_JSON','null')),os.getenv('REVIEW_BUILD_SHA256',''))
    server=make_server(store,host,port,os.getenv('REVIEW_PUBLIC_ORIGIN'));server.stream_ports=json.loads(os.getenv('REVIEW_STREAM_PORTS','[]'));server.cookie_name=os.getenv('REVIEW_COOKIE_NAME','review_session');stop=threading.Event()
    from participants import Participants
    entry_config=json.loads(pathlib.Path(os.environ['REVIEW_PARTICIPANTS_FILE']).read_text()) if os.getenv('REVIEW_PARTICIPANTS_FILE') else {'mode':'token'}
    server.participants=Participants(store,entry_config)
    server.local_autologin_owner=os.getenv('REVIEW_LOCAL_AUTOLOGIN_OWNER','')
    if server.local_autologin_owner and (host not in ('127.0.0.1','localhost') or urlparse(server.public_origin).hostname not in ('127.0.0.1','localhost')):raise ValueError('Local auto-login requires loopback-only binding and origin')
    if any(type(p)!=int or not 1024<=p<=65535 for p in server.stream_ports):raise ValueError('Invalid loopback stream ports')
    def sweep():
        while not stop.wait(1):store.tick()
    worker=threading.Thread(target=sweep,daemon=True);worker.start()
    def terminate(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,terminate)
    print(f'Review service http://{host}:{server.server_port} mode={mode}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        stop.set();worker.join(timeout=20);server.server_close()
        if not worker.is_alive():
            with store.lock:
                store.db.execute("UPDATE sessions SET status=CASE WHEN slot IS NULL THEN 'closed' ELSE 'closing' END,stream_url=NULL WHERE status IN ('queued','starting','ready','resetting','switching')");store.db.commit()
            store.tick()
        if not worker.is_alive():store.db.close()
if __name__=='__main__':main()
