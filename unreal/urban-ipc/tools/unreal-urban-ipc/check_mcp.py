"""Exercise the actual stdio MCP server against one freshly served Urban task."""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]


async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', required=True)
    p.add_argument('--task', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    cfg = {'upstream': str(ROOT/'out/native-agents/game-auditing'),
           'run_dir': str(a.out/'episode'), 'environment': 'unreal-http',
           'environment_url': a.url, 'task': a.task, 'seed': 0,
           'instruction': 'Operator transport verification; no model inference or bug grading.',
           'scene_description': 'An urban street with sidewalks, buildings and street furniture.',
           'max_actions': 5, 'max_tool_calls': 30, 'observation': 'on-demand'}
    config = a.out / 'config.json'
    config.write_text(json.dumps(cfg))
    params = StdioServerParameters(command=sys.executable,
        args=[str(ROOT/'auditor/mcp_agent/server.py'), '--config', str(config)])
    records = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert {'observe', 'inspect', 'move', 'turn', 'look', 'interact', 'wait', 'done'} <= tools
            calls = [('observe', {}), ('wait', {'seconds': 2}),
                     ('inspect', {'refs': ['a0', 'a1.f0', 'a1.f3']}),
                     ('turn', {'degrees': 45}), ('move', {'direction': 'forward', 'distance_m': 1}),
                     ('look', {'degrees': 10}), ('interact', {}),
                     ('done', {'summary': 'Urban live MCP transport smoke completed; no model evaluation.'})]
            for name, args in calls:
                result = await session.call_tool(name, args)
                text = '\n'.join(c.text for c in result.content if c.type == 'text')
                assert not result.isError, (name, text)
                images = [c for c in result.content if c.type == 'image']
                if name in {'observe', 'wait'}:
                    assert len(images) == 1
                if name == 'inspect':
                    assert len(images) == 3
                for i, image in enumerate(images):
                    suffix = '.png' if image.mimeType == 'image/png' else '.jpg'
                    (a.out/f'{name}-{i}{suffix}').write_bytes(base64.b64decode(image.data))
                records.append({'tool': name, 'arguments': args, 'text': text, 'images': len(images)})
                print(name, 'PASS', len(images), 'images', flush=True)
    meta = json.loads((a.out/'episode/meta.json').read_text())
    assert meta['status'] == 'completed' and meta['actions_used'] == 5
    (a.out/'result.json').write_text(json.dumps({'status': 'PASS', 'task': a.task,
        'records': records, 'model_inference': False}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
