"""Behavioural verification of the reef bug catalogue (analogue of harness/hs_verify.py): teleports/keyboard via
BenchmarkWorld, checks state and object flags. Prints PASS/FAIL per check."""
import json, math, os
os.makedirs('/mnt/data3/jingbo/game-auditing/runs/wt-verify', exist_ok=True)
from playwright.sync_api import sync_playwright
ARGS=["--no-sandbox","--disable-dev-shm-usage","--enable-webgl","--ignore-gpu-blocklist","--use-angle=gl-egl"]
f='/mnt/data3/jingbo/game-auditing/candidate_environments/10_beautiful_water_clean_constrained.html'
results=[]
def check(name, ok, info=''): results.append((name, ok, info)); print(('PASS' if ok else 'FAIL'), name, info)
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,args=ARGS)
    def open_bug(bid):
        pg=b.new_page(viewport={'width':960,'height':600}); pg.goto(f'file://{f}?bug={bid}' if bid else f'file://{f}', wait_until='load', timeout=300000)
        for i in range(60):
            if pg.evaluate("() => window.BenchmarkWorld && window.BenchmarkWorld.ready"): break
            pg.wait_for_timeout(500)
        return pg
    def tp(pg,x,y,z,yaw,pitch=0): pg.evaluate("([x,y,z,yaw,pitch]) => { const B=window.BenchmarkWorld; B.teleport(x,y,z); B.setView(yaw,pitch); }", [x,y,z,yaw,pitch]); pg.wait_for_timeout(300)
    def pos(pg): return pg.evaluate("() => window.BenchmarkWorld.getState().position")
    def swim(pg, ms): pg.keyboard.down('KeyW'); pg.wait_for_timeout(ms); pg.keyboard.up('KeyW'); pg.wait_for_timeout(200)
    # --- clean: rocks are solid (swim into the boulder at (5,12.5) from the south) and open water is free
    pg=open_bug(None); tp(pg, 5.0, -5.3, 15.5, 0.0); p0=pos(pg)
    # solid rock = the diver is never inside the boulder's collider while swimming through its lane (it slides over/around it)
    pg.keyboard.down('KeyW'); mins=[]
    for i in range(25):
        pg.wait_for_timeout(100)
        mins.append(pg.evaluate("() => { const B=window.BenchmarkWorld; const p=B.camera.position; let best=9; for (const c of B.player.colliders) { if (!c.obj) continue; const n=Math.sqrt(((p.x-c.x)/c.rx)**2+((p.y-c.y)/c.ry)**2+((p.z-c.z)/c.rz)**2); if (n<best) best=n; } return best; }"))
    pg.keyboard.up('KeyW'); pg.wait_for_timeout(200); p1=pos(pg)
    check('clean: boulder is solid (diver never inside its collider)', min(mins) > 0.9, f'min normalised distance {min(mins):.2f}; z {p0[2]:.1f}->{p1[2]:.1f} y {p0[1]:.1f}->{p1[1]:.1f}')
    tp(pg, -3.0, -3.0, 18.0, 0.0); p0=pos(pg); swim(pg, 2500); p1=pos(pg); check('clean: open water free', p0[2]-p1[2] > 4, f'moved {p0[2]-p1[2]:.1f} m')
    pg.close()
    # --- wt05 airwall at z 7.6..8.1 across x -4..4
    pg=open_bug('wt05-airwall'); tp(pg, 0.0, -2.0, 10.5, 0.0); p0=pos(pg); swim(pg, 2500); p1=pos(pg)
    check('wt05: invisible wall blocks', p1[2] > 8.3 and p0[2]-p1[2] < 2.4, f'z {p0[2]:.1f}->{p1[2]:.1f}'); pg.close()
    # --- wt06 hole at (1.5,4.0) r1.6: swim over it and sink / respawn
    pg=open_bug('wt06-hole'); tp(pg, 1.5, -5.0, 6.5, 0.0); y0=pos(pg)[1]; swim(pg, 1800); pg.wait_for_timeout(2500); p1=pos(pg)
    check('wt06: diver drops through the sand and respawns at the start', p1[1] < y0-0.8 or (abs(p1[0])<0.05 and abs(p1[1]+1.6)<0.05), f'y {y0:.2f}->{p1[1]:.2f} pos {[round(v,1) for v in p1]}'); pg.close()
    # --- wt07 ghost rock at (10.6,0.6): swim through it from the south
    pg=open_bug('wt07-ghostrock'); tp(pg, 10.6, -4.5, 3.4, 0.0); p0=pos(pg); swim(pg, 2600); p1=pos(pg)
    check('wt07: ghost rock passable', p1[2] < -0.5, f'z {p0[2]:.1f}->{p1[2]:.1f}'); pg.close()
    # --- wt10 backcull: visibility from south vs north
    pg=open_bug('wt10-backcull'); tp(pg, -12.5, -4.5, 16.0, 0.0); pg.wait_for_timeout(400)
    vs=pg.evaluate("() => { let r=null; window.BenchmarkWorld.scene.traverse(o=>{ if(o.name==='ROCK' && Math.abs(o.position.x+12.5)<0.6 && Math.abs(o.position.z-11.5)<0.6) r=o; }); return r && r.visible; }")
    tp(pg, -12.5, -4.5, 7.0, math.pi); pg.wait_for_timeout(400)
    vn=pg.evaluate("() => { let r=null; window.BenchmarkWorld.scene.traverse(o=>{ if(o.name==='ROCK' && Math.abs(o.position.x+12.5)<0.6 && Math.abs(o.position.z-11.5)<0.6) r=o; }); return r && r.visible; }")
    check('wt10: rock visible from south, hidden from north', vs is True and vn is False, f'south {vs} north {vn}'); pg.close()
    # --- wt12 unload: visit, leave, check cluster hidden
    pg=open_bug('wt12-unload'); tp(pg, -13.0, -4.5, 10.5, 0.0); pg.wait_for_timeout(600); tp(pg, 0.0, -2.0, 11.5, 0.0); pg.wait_for_timeout(600)
    hidden=pg.evaluate("() => { let n=0,h=0; window.BenchmarkWorld.reef.traverse(o=>{ if(/^CORAL_/.test(o.name) && Math.hypot(o.position.x+13,o.position.z-8.5)<3.2){ n++; if(!o.visible) h++; } }); return [n,h]; }")
    check('wt12: cluster unloaded after leaving', hidden[0]>0 and hidden[1]==hidden[0], f'{hidden[1]}/{hidden[0]} hidden'); pg.close()
    # --- wt13 state reset: rock moves after leave/return
    pg=open_bug('wt13-statereset'); rp=lambda: pg.evaluate("() => { let r=null; window.BenchmarkWorld.scene.traverse(o=>{ if(o.name==='ROCK' && Math.abs(o.position.x+15.5)<2.6 && Math.abs(o.position.z-5.5)<2.6) r=o; }); return r && r.position.toArray(); }")
    tp(pg, -15.5, -4.5, 9.0, 0.0); pg.wait_for_timeout(500); a=rp(); tp(pg, 0.0, -2.0, 11.5, 0.0); pg.wait_for_timeout(600); bpos=rp()
    check('wt13: rock jumped after leaving', a and bpos and math.hypot(a[0]-bpos[0], a[2]-bpos[2])>1.5, f'{[round(v,1) for v in a]} -> {[round(v,1) for v in bpos]}'); pg.close()
    # --- wt14 lod pop: proxies visible far, corals near
    pg=open_bug('wt14-lodpop'); q="() => { let c=0,cv=0,px=0,pv=0; window.BenchmarkWorld.reef.traverse(o=>{ if(/^CORAL_/.test(o.name) && Math.hypot(o.position.x-12,o.position.z-1)<3){ c++; if(o.visible) cv++; } if(o.geometry && o.geometry.type==='IcosahedronGeometry'){ px++; if(o.visible) pv++; } }); return [c,cv,px,pv]; }"
    tp(pg, 12.0, -3.5, 9.0, 0.0); pg.wait_for_timeout(400); far=pg.evaluate(q); tp(pg, 12.0, -4.0, 3.5, 0.0); pg.wait_for_timeout(400); near=pg.evaluate(q)
    check('wt14: far=proxies, near=corals', far[1]==0 and far[3]==far[2] and near[1]==near[0] and near[3]==0, f'far {far} near {near}'); pg.close()
    # --- wt16 fish reverse: heading vs velocity for the 3-fish school
    for bid,key in [('wt16-fishreverse','reverse'),('wt17-fishupside','upsideDown')]:
        pg=open_bug(bid); pg.wait_for_timeout(1500)
        r=pg.evaluate("""(key) => new Promise(res => { const B=window.BenchmarkWorld; const T=B.THREE; let mesh=null; B.scene.traverse(o=>{ if(o.isInstancedMesh && o.name==='FISH_BARRAMUNDI' && ((key==='reverse' && o.count===3) || (key==='upsideDown' && o.count===9))) mesh=o; });
          const m=new T.Matrix4(); mesh.getMatrixAt(0,m); const p0=new T.Vector3().setFromMatrixPosition(m);
          setTimeout(()=>{ mesh.getMatrixAt(0,m); const p1=new T.Vector3().setFromMatrixPosition(m); const q=new T.Quaternion().setFromRotationMatrix(m); const fwd=new T.Vector3(0,0,1).applyQuaternion(q); const up=new T.Vector3(0,1,0).applyQuaternion(q); const v=p1.clone().sub(p0).normalize(); res({dot:+v.dot(fwd).toFixed(2), upY:+up.y.toFixed(2)}); }, 600); })""", key)
        if key=='reverse': check('wt16: big fish move opposite to their heading', r['dot'] < -0.5, str(r))
        else: check('wt17: school rolled upside down', r['upY'] < -0.5, str(r))
        pg.close()
    # --- clean fish sanity: heading == velocity
    pg=open_bug(None); pg.wait_for_timeout(1500)
    r=pg.evaluate("""() => new Promise(res => { const B=window.BenchmarkWorld; const T=B.THREE; let mesh=null; B.scene.traverse(o=>{ if(o.isInstancedMesh && o.name==='FISH_BARRAMUNDI' && o.count===3) mesh=o; });
      const m=new T.Matrix4(); mesh.getMatrixAt(0,m); const p0=new T.Vector3().setFromMatrixPosition(m);
      setTimeout(()=>{ mesh.getMatrixAt(0,m); const p1=new T.Vector3().setFromMatrixPosition(m); const q=new T.Quaternion().setFromRotationMatrix(m); const fwd=new T.Vector3(0,0,1).applyQuaternion(q); const v=p1.clone().sub(p0).normalize(); res(+v.dot(fwd).toFixed(2)); }, 600); })""")
    check('clean: fish move head-first', r > 0.5, f'dot {r}'); pg.close()
    b.close()
print(f"\n{sum(1 for _,ok,_ in results if ok)}/{len(results)} PASS")
