#!/usr/bin/env python3
import json,pathlib,sys,urllib.request
config,op,sid,map_,slot=sys.argv[1:];c=json.loads(pathlib.Path(config).read_text())
req=urllib.request.Request('http://127.0.0.1:'+str(c['supervisor_port'])+'/runtime',data=json.dumps({'operation':op,'session_id':sid,'map':map_,'slot':int(slot)}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+c['secret']})
with urllib.request.urlopen(req,timeout=13) as r:print(r.read().decode())
