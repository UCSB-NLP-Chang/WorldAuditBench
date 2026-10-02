from pathlib import Path
import subprocess,json,hashlib
w=Path("/home/ubuntu/unreal-auditor/subway-workspace/review-concourse-20260917");e=Path("/opt/UnrealEngine_5.6/Engine");p=Path("/home/ubuntu/unreal-auditor/projects/Subway/Subway.uproject");out=Path("/home/ubuntu/unreal-auditor/subway-workspace/dist/review-concourse-20260917-v1");assert not out.exists()
def run(name,cmd):
 with (w/"out"/(name+".log")).open("w") as f:subprocess.run([str(x) for x in cmd],stdout=f,stderr=subprocess.STDOUT,check=True)
 print(name,"PASS",flush=True)
run("author",[e/"Binaries/Linux/UnrealEditor-Cmd",p,"-run=pythonscript","-script="+str(w/"author.py"),"-nullrhi","-nosound","-unattended"])
run("package",[e/"Build/BatchFiles/RunUAT.sh","BuildCookRun","-WaitForUATMutex","-project="+str(p),"-platform=Linux","-clientconfig=Development","-build","-cook","-stage","-pak","-package","-archive","-archivedirectory="+str(out),"-map=/Game/Auditor/Subway/Concourse+/Game/Auditor/Subway/Platform+/Game/Auditor/Subway/Trackside","-nop4","-utf8output","-unattended","-UbtArgs=-MaxParallelActions=12 -NoUBA -WaitMutex"])
b=out/"Linux/Subway/Binaries/Linux/Subway"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
(w/"out/build.json").write_text(json.dumps({"status":"PASS","package":str(out),"binary":str(b),"binary_sha256":sha(b),"map_sha256":sha(p.parent/"Saved/Cooked/Linux/Subway/Content/Auditor/Subway/Concourse.umap")},indent=2))
