"""Merge the author's UE5 rendering settings into the new Linux project only."""
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/ubuntu/unreal-auditor/rural-workspace')
source = ROOT / 'out/author-UE5-DefaultEngine.ini'
values = {}
section = ''
for raw in source.read_text().splitlines():
    line = raw.split('//', 1)[0].strip()
    if line.startswith('['):
        section = line
    elif section == '[/Script/Engine.RendererSettings]' and '=' in line:
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
if len(values) < 20:
    raise RuntimeError('Author configuration is missing or invalid.')
# Retain the author raster/SSGI pipeline and avoid PDO-incompatible ray tracing.
values.update({'r.RayTracing': 'False', 'r.RayTracing.RayTracingProxies.ProjectEnabled': 'False',
               'r.Nanite.ProjectEnabled': 'False'})
config = ROOT / 'project/Config/DefaultEngine.ini'
lines = config.read_text().splitlines()
replace = {'[/Script/Engine.RendererSettings]', '[/Script/LinuxTargetPlatform.LinuxTargetSettings]'}
output = []
skipping = False
for line in lines:
    if line.strip().startswith('['):
        skipping = line.strip() in replace
    if not skipping:
        output.append(line)
output += ['\n[/Script/Engine.RendererSettings]'] + [f'{k}={v}' for k, v in values.items()]
output += ['', '[/Script/LinuxTargetPlatform.LinuxTargetSettings]',
           '-TargetedRHIs=SF_VULKAN_SM5', '-TargetedRHIs=SF_VULKAN_SM6',
           '+TargetedRHIs=SF_VULKAN_SM5', '']
config.write_text('\n'.join(output))
(ROOT / 'out/render-config-provenance.json').write_text(json.dumps({
    'source_url': 'https://drive.google.com/file/d/163_RXTAmArKuth7IX444ZEXMnCx9-Gvv/view',
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'renderer_settings': values,
    'linux_rhi': 'SF_VULKAN_SM5',
    'validation': 'pending_actual_render',
}, indent=2))
print('RURAL_RENDER_CONFIG_MERGED', len(values))
