#!/usr/bin/env python3
"""Build the pinned Epic UE 5.6 player and signalling server (requires Node.js 22+)."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = '8cbcbb2ce8d322f23231e0c89c7cd35ab0edb5f9'
REPOSITORY = 'https://github.com/EpicGamesExt/PixelStreamingInfrastructure.git'


def configure_loopback(root):
    # The viewer proxies HTTP/WebSocket traffic; only WebRTC media needs remote access.
    edits = {
        'SignallingWebServer/src/index.ts': [(
            'const serverOpts: IServerConfig = {\n',
            "const serverOpts: IServerConfig = {\n    streamerWsOptions: { host: '127.0.0.1' },\n"
            "    playerWsOptions: { host: '127.0.0.1' },\n    sfuWsOptions: { host: '127.0.0.1' },\n")],
        'Signalling/src/WebServer.ts': [
            ('.listen(config.httpPort, () => {', ".listen(config.httpPort, '127.0.0.1', () => {"),
            ('.listen(config.httpsPort, () => {', ".listen(config.httpsPort, '127.0.0.1', () => {")],
    }
    for relative, replacements in edits.items():
        path = root / relative
        source = path.read_text()
        for old, new in replacements:
            if new not in source:
                if source.count(old) != 1:
                    raise ValueError('Unexpected upstream source: ' + relative)
                source = source.replace(old, new)
        path.write_text(source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'out/pixel-streaming')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if not root.exists():
        root.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--no-checkout', REPOSITORY, str(root)], check=True)
        subprocess.run(['git', 'checkout', '--detach', REVISION], cwd=root, check=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if revision != REVISION:
        parser.error('Existing checkout has another revision; select an unused --root directory')
    configure_loopback(root)
    subprocess.run(['npm', 'ci'], cwd=root, check=True)
    subprocess.run(['npm', 'run', 'build:all:cjs'], cwd=root, check=True)
    if not (root / 'SignallingWebServer/www/player.html').is_file():
        raise RuntimeError('The player was not generated; inspect the frontend build output')
    print('Pixel Streaming ready: ' + str(root))


if __name__ == '__main__':
    main()
