function createBenchmarkDiveController({camera,domElement,controls,app,seabedHeight,sampleOceanSurface,harnessMode=!1}){
  let active=!1,yaw=0,pitch=-.08,lastTime=null;
  const keys=new Set;
  const spawn=new M(0,-1.48,11.5);
  const movement=new M;
  const forward=new M;
  const right=new M;
  const ui=document.querySelector(`[data-clean-dive-ui]`);
  const status=document.querySelector(`[data-clean-dive-status]`);
  const startButton=document.querySelector(`[data-clean-dive-start]`);
  const resumeButton=document.querySelector(`[data-clean-dive-resume]`);
  const resetButton=document.querySelector(`[data-clean-dive-reset]`);
  const exitButton=document.querySelector(`[data-clean-dive-exit]`);
  if(harnessMode&&ui)ui.hidden=!0;

  function applyLook(){
    camera.rotation.order=`YXZ`;
    camera.rotation.y=yaw;
    camera.rotation.x=pitch;
    camera.rotation.z=0;
  }
  function setStatus(text){
    if(status)status.textContent=text;
  }
  function reset(){
    camera.position.copy(spawn);
    yaw=0;
    pitch=-.08;
    lastTime=null;
    applyLook();
    setStatus(`潜水员已回到起点`);
  }
  function lock(){
    if(!active||document.pointerLockElement===domElement)return;
    try{domElement.requestPointerLock?.()}catch{setStatus(`请点击画面继续控制`)}
  }
  function start(){
    if(harnessMode)return;
    active=!0;
    controls.enabled=!1;
    app.classList.add(`is-clean-dive-active`);
    reset();
    lock();
  }
  function exit(){
    active=!1;
    keys.clear();
    document.exitPointerLock?.();
    controls.enabled=!0;
    app.classList.remove(`is-clean-dive-active`,`is-clean-dive-locked`);
    camera.position.set(7.8,3.65,10.8);
    controls.target.set(0,.54,0);
    controls.update();
    setStatus(`观察模式`);
  }
  function onKeyDown(event){
    if(!active)return;
    if([`Space`,`Tab`].includes(event.code))event.preventDefault();
    keys.add(event.code);
    if(!event.repeat&&event.code===`KeyR`)reset();
  }
  function onKeyUp(event){keys.delete(event.code)}
  function onMouseMove(event){
    if(!active||document.pointerLockElement!==domElement)return;
    yaw-=event.movementX*.00215;
    pitch-=event.movementY*.00215;
    pitch=yi.clamp(pitch,-1.42,1.42);
    applyLook();
  }
  function onPointerLock(){
    const locked=document.pointerLockElement===domElement;
    app.classList.toggle(`is-clean-dive-locked`,active&&locked);
    if(locked)setStatus(`正在探索高质量浅海环境`);
    else if(active)setStatus(`已暂停 · 点击画面继续`);
    if(!locked)keys.clear();
  }

  startButton?.addEventListener(`click`,start);
  resumeButton?.addEventListener(`click`,lock);
  resetButton?.addEventListener(`click`,reset);
  exitButton?.addEventListener(`click`,exit);
  domElement.addEventListener(`click`,()=>{
    if(active&&document.pointerLockElement!==domElement)lock();
  });
  window.addEventListener(`keydown`,onKeyDown);
  window.addEventListener(`keyup`,onKeyUp);
  window.addEventListener(`mousemove`,onMouseMove);
  document.addEventListener(`pointerlockchange`,onPointerLock);

  const api={
    isActive:()=>active,
    start,
    exit,
    reset,
    setPosition(position){
      if(Array.isArray(position)&&position.length===3)camera.position.fromArray(position);
      return api.getState();
    },
    getState(){
      return{
        active,
        pointerLocked:document.pointerLockElement===domElement,
        position:camera.position.toArray(),
        rotation:{yaw,pitch}
      };
    },
    update(time){
      const delta=lastTime===null?0:yi.clamp(time-lastTime,0,.05);
      lastTime=time;
      if(!active||document.pointerLockElement!==domElement)return;
      forward.set(-Math.sin(yaw),0,-Math.cos(yaw));
      right.set(Math.cos(yaw),0,-Math.sin(yaw));
      movement.set(0,0,0);
      if(keys.has(`KeyW`))movement.add(forward);
      if(keys.has(`KeyS`))movement.sub(forward);
      if(keys.has(`KeyD`))movement.add(right);
      if(keys.has(`KeyA`))movement.sub(right);
      if(keys.has(`Space`))movement.y+=1;
      if(keys.has(`KeyC`)||keys.has(`ControlLeft`)||keys.has(`ControlRight`))movement.y-=1;
      if(movement.lengthSq()>0){
        movement.normalize();
        const speed=keys.has(`ShiftLeft`)||keys.has(`ShiftRight`)?6:3.15;
        camera.position.addScaledVector(movement,speed*delta);
        camera.position.x=yi.clamp(camera.position.x,-27,27);
        camera.position.z=yi.clamp(camera.position.z,-27,27);
      }
      const bottom=seabedHeight(camera.position.x,camera.position.z)+.52;
      const surface=sampleOceanSurface(camera.position.x,camera.position.z,time).height-.38;
      camera.position.y=yi.clamp(camera.position.y,bottom,Math.max(bottom+.1,surface));
      applyLook();
    }
  };
  return api;
}
function GJ(e){benchmarkDiveController?.update(e);if(!benchmarkDiveController?.isActive()){vY||BY.target.set(qY.mesh.position.x,qY.mesh.position.y+.62,qY.mesh.position.z),BY.update();let t=tK(BY.target.x,BY.target.z)+.22;BY.target.y=Math.max(BY.target.y,t);let n=tK(zY.position.x,zY.position.z)+.3;zY.position.y<n&&(zY.position.y=n,BY.update())}let r=dK(zY.position.x,zY.position.z,e),i=+(zY.position.y<r.height);lX=i>.5,$Y=vY?oX??i:yi.lerp($Y,i,.085),WY.update(e,$Y),UY.update(e,$Y,zY),GY.update(e,$Y),KY.update(e,$Y,zY),qY.update(e,$Y),JY.update(e,$Y,zY),RY.fog.density=yi.lerp(.0017,.038,$Y),OY.toneMappingExposure=yi.lerp(.9,.76,$Y),aY.classList.toggle(`is-underwater`,$Y>.5)}
function KJ(e=`both`){WY.usesManualCaptures&&(YY.forEach(e=>{e.visible=!0}),$Y<.65&&(e===`reflection`?WY.renderReflectionCapture(qY.captureHiddenObjects):e===`refraction`?WY.renderRefractionCapture(qY.captureHiddenObjects):WY.renderCaptures(qY.captureHiddenObjects)),lX||YY.forEach(e=>{e.visible=!1}))}function qJ(){OY.render(RY,zY),(!vY||sX)&&JY.render(OY),cX=U_(OY)}function JJ(e){OY.info.reset(),MY.beginFrame();try{let t=NY.getState();uX%t.shadowFrameInterval===0&&(OY.shadowMap.needsUpdate=!0,GY.requestShadowUpdate()),GJ(e),KJ(),qJ()}finally{MY.endFrame()}uX+=1}function YJ(e){return Number.isFinite(e)?e<20?e.toFixed(1):String(Math.round(e)):`--`}function XJ(){return typeof window.screen?.isExtended==`boolean`?window.screen.isExtended:null}function ZJ(){let e=XJ(),t=xY.getCap(),n=t===null?`CAP OFF`:`CAP ${t}`;mY.textContent=e===!0?`${n} / MULTI-SCREEN / PANEL HZ UNKNOWN`:`${n} / PANEL HZ UNKNOWN`}function QJ(e){let t=xY.getCap()??e.refreshRateFps??Math.max(60,e.averageFps??0);dY.setAttribute(`d`,I_(e.series,{targetFps:t})),fY.textContent=YJ(e.averageFps),pY.textContent=YJ(e.onePercentLowFps),uY.setAttribute(`aria-label`,`Rendered frames per second over the last ${(e.windowElapsedMs/1e3).toFixed(1)} seconds: ${YJ(e.averageFps)} average, ${YJ(e.onePercentLowFps)} one-percent low`);let n=e.windowElapsedMs>=2e3&&Number.isFinite(e.worstOneSecondFps)&&Number.isFinite(t)&&e.worstOneSecondFps<t*.75;lY.classList.toggle(`has-frame-drop`,n)}function $J(e=performance.now()){eX+=1;let t=e-tX;if(t<500)return;let n=eX*1e3/t;nX=Number.isFinite(nX)?yi.lerp(nX,n,.42):n,oY.textContent=YJ(nX);let r=MY.getState(),i=e=>Number.isFinite(e)?e.toFixed(e<10?2:1):`--`;sY.textContent=r.ready?i(r.medianFrameTimeMs):`--`,cY.textContent=r.ready?i(r.p95FrameTimeMs):`--`,rX=FY.getState(e),iX=IY.getState(e),QJ(iX),eX=0,tX=e}function eY(e){let t=document.createElement(`textarea`);t.value=e,t.setAttribute(`readonly`,``),t.style.position=`fixed`,t.style.opacity=`0`,t.style.pointerEvents=`none`,document.body.append(t),t.select(),t.setSelectionRange(0,t.value.length);let n=document.execCommand(`copy`);if(t.remove(),!n)throw Error(`Clipboard copy was rejected`)}async function tY(e){if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(e);return}eY(e)}function nY(){let e=performance.now();rX=FY.getState(e),iX=IY.getState(e);let t=NY.getState();return R_({capturedAt:new Date().toISOString(),presentation:rX,rendering:iX,renderCapFps:xY.getCap(),gpu:MY.getState(),renderer:{pipeline:DY.pipeline,backend:DY.backend,adapter:DY.adapterName??kY.renderer},canvas:{drawingBufferWidth:OY.domElement.width,drawingBufferHeight:OY.domElement.height,cssWidth:window.innerWidth,cssHeight:window.innerHeight},quality:t,scene:lX?`underwater`:`surface`,drawCalls:cX.drawCalls,triangles:cX.triangles,pageState:{visibility:document.visibilityState,focused:document.hasFocus(),devicePixelRatio:window.devicePixelRatio,multipleScreens:XJ()},pageUrl:window.location.href,runtime:_Y})}async function rY(){await CY.paint(.36,`Compiling water and reflections`),await Promise.all([OY.compileAsync(RY,zY),WY.compileCaptures(qY.captureHiddenObjects)]),GJ(vY?aX:0),await CY.paint(.7,`Warming reflection`),OY.shadowMap.needsUpdate=!0,GY.requestShadowUpdate(),KJ(`reflection`),await CY.paint(.82,`Warming refraction`),KJ(`refraction`),await CY.paint(.94,`Opening water`),qJ(),vY&&(window.__WATER_HARNESS__={ready:!1,setView({position:e,target:t,time:n=aX,renderPasses:r=2,underwaterBlend:i=null}){aX=n,oX=Number.isFinite(i)?yi.clamp(i,0,1):null,zY.position.fromArray(e),BY.target.fromArray(t),zY.updateMatrixWorld(),BY.update();let a=yi.clamp(Math.round(r),1,2);for(let e=0;e<a;e+=1)JJ(aX);return this.getDiagnostics()},getDiagnostics(){let e=NY.getState();return{camera:zY.position.toArray(),target:BY.target.toArray(),underwater:$Y>.5,underwaterMix:$Y,drawCalls:cX.drawCalls,triangles:cX.triangles,programs:OY.info.programs?.length??+(cX.drawCalls>0),quality:{...e,antialias:EY,canvasSize:[OY.domElement.width,OY.domElement.height],ocean:WY.getDiagnostics(),environment:GY.getDiagnostics()},renderer:{preferred:wY,pipeline:DY.pipeline,backend:DY.backend,adapter:DY.adapterName,fallbackReason:DY.fallbackReason},performance:MY.getState(),controls:{orbitPivot:`buoy`,panEnabled:BY.enablePan,zoomToCursor:BY.zoomToCursor},fish:KY.getDiagnostics(zY)}},advance({duration:e=1,step:t=1/30}={}){let n=aX+Math.max(0,e),r=yi.clamp(t,1/120,1/20);for(;aX+1e-4<n;)aX=Math.min(aX+r,n),GJ(aX);return JJ(aX),this.getDiagnostics()},setUnderwaterRaysEnabled(e){sX=!!e,qJ()},samplePerformance({fps:e,samples:t=1}){let n=!1;for(let r=0;r<t;r+=1)n=NY.sampleFrameRate(e)||n;return n&&zJ(),this.getDiagnostics()}},JJ(aX)),await CY.reveal(),vY?window.__WATER_HARNESS__.ready=!0:(eX=0,tX=performance.now(),nX=null,FY.reset(),IY.reset(),xY.reset(),OY.setAnimationLoop(e=>{if(FY.recordFrame(e),document.hidden||(NY.sampleGpuTiming(MY.getState())||NY.observeFrame(e))&&BJ(),!xY.shouldRender(e))return;let t=performance.now();IY.recordFrame(e),ZY.update(),JJ(ZY.getElapsed()),$J(e);let n=performance.now()-t;IY.recordCpuFrame(e,n),yY&&(dX.push(n),dX.length>2e4&&dX.shift())}),yY&&(window.__WATER_PERFORMANCE__.ready=!0))}var iY,aY,oY,sY,cY,lY,uY,dY,fY,pY,mY,hY,gY,_Y,vY,yY,bY,xY,SY,CY,wY,TY,EY,DY,OY,kY,AY,jY,MY,NY,PY,FY,IY,LY,RY,zY,BY,VY,HY,UY,WY,GY,KY,qY,JY,YY,XY,ZY,QY,$Y,eX,tX,nX,rX,iX,aX,oX,sX,cX,lX,uX,dX,fX,pX=t((async()=>{vg(),Hg(),p_(),y_(),k_(),V_(),W_(),GG(),eK(),xK(),oK(),jK(),AJ(),gK(),NJ(),FJ(),LJ(),iY=document.querySelector(`#ocean-canvas`),aY=document.querySelector(`#app`),oY=document.querySelector(`[data-fps]`),sY=document.querySelector(`[data-gpu-p50]`),cY=document.querySelector(`[data-gpu-p95]`),lY=document.querySelector(`[data-performance-panel]`),uY=document.querySelector(`[data-fps-history]`),dY=document.querySelector(`[data-fps-history-line]`),fY=document.querySelector(`[data-fps-average]`),pY=document.querySelector(`[data-fps-low]`),mY=document.querySelector(`[data-display-note]`),hY=document.querySelector(`[data-performance-copy]`),gY=new URLSearchParams(window.location.search),_Y=QG(navigator),vY=gY.has(`harness`),yY=!vY&&gY.get(`sustain`)===`native-4k`,bY=yY?null:C_(gY),xY=T_(bY),SY=Math.min(bY??60,60),CY=MJ(aY),CY.setStage(.1,`Building ocean surface`),wY=RG(gY),TY=Jg({width:window.innerWidth,height:window.innerHeight,devicePixelRatio:window.devicePixelRatio}),EY=wY===`webgl`&&TY,await CY.paint(.16,wY===`webgpu`?`Starting WebGPU`:`Starting WebGL`),DY=await HG({canvas:iY,antialias:EY,preferredMode:wY}),OY=DY.renderer,IJ(document.querySelector(`[data-renderer-toggle]`),DY),OY.outputColorSpace=Lr,OY.toneMapping=4,OY.toneMappingExposure=.9,OY.shadowMap.enabled=!0,OY.shadowMap.type=1,DY.pipeline===`webgl`&&(OY.shadowMap.autoUpdate=!1),kY=qg(OY,{rendererName:DY.adapterName,deviceMemory:navigator.deviceMemory,hardwareConcurrency:navigator.hardwareConcurrency}),AY=gY.get(`gpuClass`),jY=vY&&[`software`,`integrated`,`unknown`,`discrete`].includes(AY)?AY:kY.gpuClass,MY=g_(OY),NY=Qg({width:window.innerWidth,height:window.innerHeight,devicePixelRatio:window.devicePixelRatio,gpuClass:jY,rendererName:kY.renderer,lockedPixelRatio:yY?1:null,gpuTimingEnabled:!vY&&MY.supported,targetFrameRate:SY}),PY=NY.getState(),FY=F_(),IY=F_(),await CY.paint(.24,`Loading water pipeline`),LY=await kJ(DY.pipeline),RY=new wa,RY.fog=new Sa(408648,1e-5),RY.background=new P(408648),zY=new Vu(51,1,.08,520),zY.position.set(7.8,3.65,10.8),BY=new Vg(zY,OY.domElement),BY.target.set(0,.54,0),BY.enableDamping=!vY,BY.dampingFactor=.055,BY.enablePan=!1,BY.screenSpacePanning=!1,BY.minDistance=2.7,BY.maxDistance=46,BY.minPolarAngle=.055,BY.maxPolarAngle=Math.PI-.055,BY.zoomToCursor=!1,BY.update(),!vY&&gY.get(`profileView`)===`underwater`&&(zY.position.set(7.5,-2.15,9.8),BY.target.set(0,-1.75,0),BY.update()),BY.addEventListener(`start`,()=>aY.classList.add(`is-orbiting`)),BY.addEventListener(`end`,()=>aY.classList.remove(`is-orbiting`)),VY=new M(-.58,.1,-.81).normalize(),HY=jY===`discrete`?300:jY===`unknown`?240:DY.pipeline===`webgpu`?180:210,UY=LY.createSky(RY,VY),WY=DY.pipeline===`webgpu`?LY.createOcean({renderer:OY,scene:RY,sunDirection:VY,captureResolution:PY.captureResolution,surfaceSegments:HY}):LY.createOcean({renderer:OY,scene:RY,camera:zY,sunDirection:VY,sky:UY,sun:UY.sun,captureResolution:PY.captureResolution,surfaceSegments:HY}),GY=iK(RY,VY,{shadowMapResolution:PY.shadowMapResolution,rendererMode:DY.pipeline}),KY=wK(RY),qY=bK(RY,VY,{rendererMode:DY.pipeline}),JY=LY.createUnderwaterRays(VY),
YY=[...GY.underwaterObjects,...KY.underwaterObjects,...qY.underwaterObjects],
