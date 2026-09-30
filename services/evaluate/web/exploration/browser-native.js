/* Keep native game controls; add frame capture without review/debug shortcuts. */
(() => {
  const original=HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext=function(type,options){
    const webgl=/^webgl2?$|experimental-webgl/.test(type);
    const context=original.call(this,type,webgl?{...options,preserveDrawingBuffer:true}:options);
    if(webgl&&context&&!context.bfCaptureHook){
      context.bfCaptureHook=true;
      for(const name of ['drawArrays','drawElements']){
        const draw=context[name];context[name]=function(...args){const result=draw.apply(this,args);window.bfBrowserReady=true;return result;};
      }
    }
    return context;
  };
  document.addEventListener('keydown',e=>{
    if(['Backquote'].includes(e.code)){e.preventDefault();e.stopImmediatePropagation();}
  },true);
})();
