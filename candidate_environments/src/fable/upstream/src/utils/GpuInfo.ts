export interface GpuInfo {
  vendor: string | null;
  renderer: string | null;
}

/** Read the active WebGL adapter (requires WEBGL_debug_renderer_info). */
export function getGpuInfo(gl: WebGLRenderingContext | WebGL2RenderingContext): GpuInfo {
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  if (!ext) return { vendor: null, renderer: null };
  return {
    vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) as string,
    renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) as string,
  };
}

export function logGpuInfo(gl: WebGLRenderingContext | WebGL2RenderingContext): GpuInfo {
  const info = getGpuInfo(gl);
  if (!info.renderer) {
    console.info('[gpu] Renderer info unavailable (debug extension blocked).');
    return info;
  }

  console.info(`[gpu] ${info.vendor} — ${info.renderer}`);
  return info;
}
