from pathlib import Path
import subprocess,concurrent.futures
w=Path('/home/ubuntu/unreal-auditor/subway-workspace/s20-car-replacement')
def job(names):
 for n,args in names:
  with (w/'out'/(n+'-driver.log')).open('w') as f:subprocess.run(['python3',str(w/'scripts'/(n+'.py')),*args],stdout=f,stderr=subprocess.STDOUT,check=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 jobs=[pool.submit(job,[('regression',['subway']),('reuse',['subway'])]),pool.submit(job,[('render',[]),('walk',[])]),pool.submit(job,[('prepare',[])])]
 for j in jobs:j.result()
print('VERIFY_PASS')
