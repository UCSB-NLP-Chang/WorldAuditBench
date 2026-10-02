import sys,json,os
from pathlib import Path
stage=Path(sys.argv[1]);sys.path.insert(0,str(stage));import server
p=Path(os.getenv('MEDIEVAL_MOCK_OUTPUT','/home/ubuntu/unreal-auditor/medieval-workspace/out/mock-review'));p.mkdir(parents=True,exist_ok=True)
port=int(os.getenv('MEDIEVAL_MOCK_PORT','19509'))
s=server.Store(p/'qa.sqlite3',json.loads((stage/'tasks.json').read_text()),capacity=3);h=server.make_server(s,host='127.0.0.1',port=port)
print('Isolated candidate UI on '+str(port),flush=True)
try:h.serve_forever()
finally:h.server_close();s.db.close()
