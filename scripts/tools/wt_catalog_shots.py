import json, math, sys
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw
ARGS=["--no-sandbox","--disable-dev-shm-usage","--enable-webgl","--ignore-gpu-blocklist","--use-angle=gl-egl"]
f='/mnt/data3/jingbo/game-auditing/candidate_environments/10_beautiful_water_clean_constrained.html'
S='/mnt/data3/jingbo/game-auditing/reports/water-suite/catalog'
import os; os.makedirs(S, exist_ok=True)
BUGS=['wt01-float','wt02-clip','wt03-scale','wt04-doublespawn','wt05-airwall','wt06-hole','wt07-ghostrock','wt08-jitter','wt09-magenta','wt10-backcull','wt11-xray','wt12-unload','wt13-statereset','wt14-lodpop','wt15-spawnpile','wt16-fishreverse','wt17-fishupside']
# viewpoint offsets (dx, dz) from the answer position, camera distance; default: from the spawn side (+z)
OFF={'wt10-backcull':(0,+4.5),'wt11-xray':(0.5,-7.0),'wt05-airwall':(0,+4.0),'wt06-hole':(0,+3.5),'wt16-fishreverse':(4,4),'wt17-fishupside':(4,4),'wt03-scale':(2,7.5),'wt14-lodpop':(0,7.0),'wt02-clip':(2.5,3.5),'wt04-doublespawn':(3,5),'wt08-jitter':(3.0,4.0)}
rows=[]
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,args=ARGS)
    for bid in BUGS:
        pg=b.new_page(viewport={'width':1280,'height':800}); msgs=[]; pg.on('pageerror', lambda e: msgs.append(str(e)[:120]))
        pg.goto(f'file://{f}?bug={bid}', wait_until='load', timeout=300000)
        for i in range(60):
            if pg.evaluate("() => window.BenchmarkWorld && window.BenchmarkWorld.ready"): break
            pg.wait_for_timeout(500)
        ans=pg.evaluate("() => window.BenchmarkWorld.bug")
        if not ans: print(bid, 'NO ANSWER', msgs[:2]); pg.close(); continue
        ax,ay,az=ans['at']; dx,dz=OFF.get(bid,(0,4.0)); dist=math.hypot(dx,dz)
        cx,cz=ax+dx,az+dz; cy=min(-0.6, ay+1.0)
        yaw=math.atan2(-(ax-cx), -(az-cz)); pitch=math.atan2(ay-cy, dist)
        pg.evaluate("([x,y,z,yaw,pitch]) => { const B=window.BenchmarkWorld; B.teleport(x,y,z); B.setView(yaw,pitch); }", [cx,cy,cz,yaw,pitch])
        pg.wait_for_timeout(900); pg.screenshot(path=f'{S}/{bid}.png')
        st=pg.evaluate("() => window.BenchmarkWorld.getState().position")
        rows.append((bid, ans['name'])); print(bid, ans['name'], 'cam', [round(v,1) for v in st], 'errors', msgs[:1])
        pg.close()
    b.close()
w,h=640,400; cols=3; n=len(rows); r=(n+cols-1)//cols
im=Image.new('RGB',(cols*w, r*(h+16)),'black'); d=ImageDraw.Draw(im)
for i,(bid,name) in enumerate(rows):
    x=(i%cols)*w; y=(i//cols)*(h+16); im.paste(Image.open(f'{S}/{bid}.png').convert('RGB').resize((w,h)),(x,y+16)); d.text((x+4,y+2), f'{bid}: {name}', fill='white')
im.save(S+'/../catalog.jpg', quality=85); print('sheet', n)
