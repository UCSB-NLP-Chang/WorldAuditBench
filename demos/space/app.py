"""HF Docker Space: Gradio shell, browser controls, and a local Unreal runtime."""
import asyncio, contextlib, json, logging, os, re, subprocess, time
from contextlib import asynccontextmanager
from pathlib import Path
import gradio as gr
import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from websockets.asyncio.client import connect
from runtime import UnrealRuntime
from sessions import Sessions

ROOT=Path(__file__).resolve().parent
CASES=json.loads((ROOT/'cases.json').read_text())
BY_ID={c['id']:c for c in CASES}
log=logging.getLogger('worldauditbench')
class RedactSessionToken(logging.Filter):
    def filter(self, record):
        record.msg=re.sub(r'(token=)[^&\s"\']+',r'\1[redacted]',record.getMessage())
        record.args=()
        return True
logging.getLogger('uvicorn.error').addFilter(RedactSessionToken())
sessions=Sessions(); lock=asyncio.Lock(); runtime=None; active=None; signalling=None
bridges=set()

def credentials(request):
    return request.headers.get('Authorization','').removeprefix('Bearer ')

def own(id,token):
    try:return sessions.owner(id,token)
    except PermissionError as e:raise HTTPException(401,str(e))

async def release(id):
    global active
    if active==id:
        await asyncio.to_thread(runtime.stop)
        active=None
    sessions.entries.pop(id,None)

async def worker():
    global active
    async with httpx.AsyncClient(timeout=2) as client:
        while True:
            try:
                async with lock:
                    for s in sessions.expired(): await release(s['id'])
                    if active:
                        s=sessions.entries[active]
                        if not runtime.alive() or signalling.poll() is not None:
                            await release(active)
                        elif s['state']=='starting':
                            if sessions.clock()-s['started']>120:
                                await release(active)
                            else:
                                try:
                                    r=await client.get('http://127.0.0.1:8889')
                                    if r.json().get('ready') and runtime.ready(s['case'],s['id']):
                                        s['state']='ready'
                                        print(f'Unreal scene ready: {s["case"]["id"]}',flush=True)
                                except (httpx.HTTPError,ValueError): pass
                    if not active and sessions.entries:
                        s=next(iter(sessions.entries.values()))
                        active=s['id']; s['state']='starting'; s['started']=sessions.clock()
                        try: await asyncio.to_thread(runtime.start,s['case'],s['id'])
                        except Exception:
                            log.exception('Unreal launch failed'); await release(s['id'])
            except Exception:log.exception('Session worker failed')
            await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app):
    global runtime,signalling
    runtime=await asyncio.to_thread(UnrealRuntime)
    task=None
    if not runtime.error:
        signalling=subprocess.Popen(['node',str(ROOT/'signalling.cjs')],cwd=ROOT)
        task=asyncio.create_task(worker())
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):await task
    await asyncio.to_thread(runtime.stop)
    if signalling:
        signalling.terminate()
        try:await asyncio.to_thread(signalling.wait,timeout=5)
        except subprocess.TimeoutExpired:signalling.kill(); await asyncio.to_thread(signalling.wait)

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None)

@app.get('/api/catalog')
def catalog():
    return {'available':bool(runtime and not runtime.error),'message':runtime.error if runtime else 'Starting…',
        'cases':[{k:c[k] for k in ('id','number','family','scene')} for c in CASES]}

@app.get('/api/answer/{case_id}')
def answer(case_id:str):
    if case_id not in BY_ID:raise HTTPException(404)
    return BY_ID[case_id]['answer']

class Start(BaseModel):
    case_id:str

@app.post('/api/session')
async def start(body:Start):
    if body.case_id not in BY_ID:raise HTTPException(404,'Unknown task')
    if not runtime or runtime.error:raise HTTPException(503,'The interactive environment is being prepared.')
    async with lock:
        try:s=sessions.create(BY_ID[body.case_id])
        except ValueError as e:raise HTTPException(429,str(e))
        return {**sessions.public(s),'token':s['token'],'transport':os.environ.get('WAB_TRANSPORT','websocket')}

@app.post('/api/session/{id}/heartbeat')
async def heartbeat(id:str,request:Request):
    async with lock:
        s=own(id,credentials(request)); s['heartbeat']=sessions.clock()
        return sessions.public(s)

@app.delete('/api/session/{id}')
async def stop(id:str,request:Request):
    async with lock:
        own(id,credentials(request)); await release(id)
    return {'stopped':True}

@app.websocket('/api/signal/{id}')
async def signal_proxy(ws:WebSocket,id:str):
    token=ws.query_params.get('token','')
    try:s=sessions.owner(id,token)
    except PermissionError:await ws.close(code=1008);return
    if active!=id or s['state']!='ready':await ws.close(code=1008);return
    await ws.accept()
    try:
        async with connect('ws://127.0.0.1:8889',max_size=2**20) as upstream:
            async def inbound():
                while True:
                    if active!=id or id not in sessions.entries:return
                    msg=await ws.receive_text()
                    await upstream.send(msg)
            async def outbound():
                async for msg in upstream:
                    if isinstance(msg,str):await ws.send_text(msg)
                    else:await ws.send_bytes(msg)
            async def lease():
                while active==id and id in sessions.entries:await asyncio.sleep(1)
            jobs=[asyncio.create_task(f()) for f in (inbound,outbound,lease)]
            try:
                done,_=await asyncio.wait(jobs,return_when=asyncio.FIRST_COMPLETED)
                for j in done:j.result()
            finally:
                for j in jobs:j.cancel()
                await asyncio.gather(*jobs,return_exceptions=True)
    except (WebSocketDisconnect,OSError):pass
    except Exception:log.info('Signalling connection closed')
    finally:
        with contextlib.suppress(Exception):await ws.close()

@app.websocket('/api/stream/{id}')
async def stream_proxy(ws:WebSocket,id:str):
    try:s=sessions.owner(id,ws.query_params.get('token',''))
    except PermissionError:await ws.close(code=1008);return
    if active!=id or s['state']!='ready' or id in bridges:
        await ws.close(code=1008);return
    bridges.add(id)
    bridge=None
    jobs=[]
    try:
        from stream_bridge import StreamBridge
        await ws.accept()
        bridge=StreamBridge()
        async def lease():
            while active==id and id in sessions.entries:await asyncio.sleep(0.5)
        jobs=[asyncio.create_task(c) for c in (bridge.signal(),bridge.send_frames(ws),bridge.receive_input(ws),lease())]
        done,_=await asyncio.wait(jobs,return_when=asyncio.FIRST_COMPLETED)
        for job in done:job.result()
    except (WebSocketDisconnect,OSError,asyncio.TimeoutError):pass
    except Exception:log.exception('Local video bridge failed')
    finally:
        for job in jobs:job.cancel()
        await asyncio.gather(*jobs,return_exceptions=True)
        if bridge:await bridge.close()
        bridges.discard(id)
        with contextlib.suppress(Exception):await ws.close()

@app.get('/explore')
def explore():return FileResponse(ROOT/'static/index.html')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
with gr.Blocks(title='WorldAuditBench · Explore') as demo:
    gr.HTML('<iframe title="WorldAuditBench interactive explorer" src="/explore" allow="autoplay; fullscreen" style="width:100%;height:960px;border:0;border-radius:16px" allowfullscreen></iframe>')
app=gr.mount_gradio_app(app,demo,path='/',css='.gradio-container {max-width: 1500px!important} footer {display:none!important}',footer_links=[])
