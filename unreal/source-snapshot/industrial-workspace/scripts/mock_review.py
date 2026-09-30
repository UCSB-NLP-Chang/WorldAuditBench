import sys,json
from pathlib import Path
r=Path('/home/ubuntu/unreal-auditor/review-service/staging/industrial-20260912');sys.path.insert(0,str(r))
import server
p=Path('/home/ubuntu/unreal-auditor/industrial-workspace/out/mock-review');p.mkdir(exist_ok=True)
s=server.Store(p/'qa.sqlite3',json.loads((r/'tasks.json').read_text()),capacity=3)
h=server.make_server(s,host='127.0.0.1',port=8098)
print('Isolated candidate UI on 8098',flush=True)
try:h.serve_forever()
finally:h.server_close();s.db.close()
