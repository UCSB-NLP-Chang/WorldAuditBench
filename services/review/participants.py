"""Team entry and stable self-selected reviewer identities; separate from token-bound operators."""
import hashlib,hmac,json,secrets,time,unicodedata

def normalized_name(name):
 if not isinstance(name,str):raise ValueError('Please enter your name.')
 name=' '.join(unicodedata.normalize('NFKC',name).split())
 if not 1<=len(name)<=80 or any(unicodedata.category(c).startswith('C') for c in name):raise ValueError('Name must contain 1–80 visible characters.')
 return name

class Participants:
 def __init__(self,store,config):
  self.store=store;self.mode=config.get('mode','token');self.code=config.get('access_code','');self.roster=config.get('reviewers',[]);self.allow_new=config.get('allow_new_names',not self.roster)
  if self.mode not in ('token','group','name'):raise ValueError('Invalid participant login mode')
  if self.mode=='group' and not self.code:raise ValueError('Group access code required')
  seen=set()
  for row in self.roster:
   key=normalized_name(row['name']).casefold()
   if not row.get('id') or key in seen:raise ValueError('Roster names and IDs must be unique')
   seen.add(key)
  if len({row['id'] for row in self.roster})!=len(self.roster):raise ValueError('Duplicate reviewer ID')
  store.db.execute('CREATE TABLE IF NOT EXISTS participants(id TEXT PRIMARY KEY,name_key TEXT UNIQUE NOT NULL,name TEXT NOT NULL,created REAL NOT NULL)');store.db.commit()
 def check(self,code):
  if self.mode=='token':raise PermissionError('Name sign-in is not enabled.')
  if self.mode=='group' and (not isinstance(code,str) or not hmac.compare_digest(code.encode(),self.code.encode())):raise PermissionError('Incorrect passcode.')
 def options(self,code):
  self.check(code)
  if self.roster:return [{'id':r['id'],'name':normalized_name(r['name'])} for r in self.roster]
  with self.store.lock:return [dict(r) for r in self.store.db.execute('SELECT id,name FROM participants ORDER BY name_key LIMIT 500')]
 def login(self,code,name):
  self.check(code);name=normalized_name(name);key=name.casefold()
  with self.store.lock:
   if self.roster:
    record=next((r for r in self.roster if normalized_name(r['name']).casefold()==key),None)
    if not record:raise ValueError('Please choose your name from the list.')
    owner='participant:'+record['id'];name=normalized_name(record['name'])
   else:
    record=self.store.db.execute('SELECT id,name FROM participants WHERE name_key=?',(key,)).fetchone()
    if record:owner,name=record['id'],record['name']
    else:
     if not self.allow_new:raise ValueError('This name is not on the reviewer list.')
     owner='participant:'+secrets.token_hex(16)
     self.store.db.execute('INSERT INTO participants VALUES(?,?,?,?)',(owner,key,name,time.time()))
   cookie=secrets.token_urlsafe(32)
   self.store.db.execute('INSERT INTO logins VALUES(?,?,?,?)',(hashlib.sha256(cookie.encode()).hexdigest(),owner,name,time.time()+43200));self.store.db.commit()
   return cookie,{'owner':owner,'reviewer':name}
