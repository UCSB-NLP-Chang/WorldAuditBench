"""Restore already-acquired Rural Australia files from the Launcher manifest.

Only the user's exact downloaded build and its public Epic CDN chunks are used.
No login state is transferred. Every chunk and output file is hash verified.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import struct
import time
import urllib.error
import urllib.request
import zlib

ROOT = Path('/home/ubuntu/unreal-auditor/rural-workspace')
OUT = ROOT / 'out'
MANIFEST = json.loads((OUT / 'source.manifest').read_text())
assert MANIFEST['AppNameString'] == 'RuralAus2b4566deea9fV7'
CDN = 'https://egdownload.fastly-edge.com/Builds/Rocket/Automated/RuralAus2b4566deea9fV7/CloudDir'
CACHE = OUT / 'cdn-chunks'
CACHE.mkdir(exist_ok=True)
DESTINATION = OUT / 'verified-source'
DESTINATION.mkdir(exist_ok=True)


def raw_number(value):
    return bytes(int(value[index:index+3]) for index in range(0, len(value), 3))


def number(value):
    return int.from_bytes(raw_number(value), 'little')


def fetch(guid):
    path = CACHE / guid
    expected = MANIFEST['ChunkShaList'][guid].lower()
    if path.exists() and hashlib.sha1(path.read_bytes()).hexdigest() == expected:
        return
    group = number(MANIFEST['DataGroupList'][guid])
    rolling = number(MANIFEST['ChunkHashList'][guid])
    url = f'{CDN}/ChunksV3/{group:02d}/{rolling:016X}_{guid}.chunk'
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=40) as response:
                encoded = response.read()
            magic, version, header, stored_size = struct.unpack_from('<IIII', encoded)
            if magic != 0xB1FE3AA2 or len(encoded) != header + stored_size:
                raise ValueError('Invalid chunk header or length: ' + guid)
            if encoded[40] & 2:
                raise ValueError('Encrypted chunk unsupported; use normal source transfer.')
            stored_guid = ''.join(f'{value:08X}' for value in struct.unpack_from('<IIII', encoded, 16))
            if stored_guid != guid:
                raise ValueError('Wrong chunk GUID')
            decoded = zlib.decompress(encoded[header:]) if encoded[40] & 1 else encoded[header:]
            if hashlib.sha1(decoded).hexdigest() != expected:
                raise ValueError('Chunk digest mismatch: ' + guid)
            path.write_bytes(decoded)
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def main():
    if number(MANIFEST['ManifestFileVersion']) != 13:
        raise RuntimeError('This importer is restricted to the verified v13 manifest.')
    guids = list(MANIFEST['ChunkShaList'])
    with ThreadPoolExecutor(max_workers=12) as executor:
        jobs = [executor.submit(fetch, guid) for guid in guids]
        for index, future in enumerate(as_completed(jobs), 1):
            future.result()
            if index % 200 == 0 or index == len(jobs):
                print('Verified chunks', index, '/', len(jobs), flush=True)
    checks = []
    for file in MANIFEST['FileManifestList']:
        relative = Path(file['Filename'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[:2] != ('Content', 'RuralAustralia'):
            raise RuntimeError('Unexpected manifest path: ' + str(relative))
        output = DESTINATION / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        sha1 = hashlib.sha1()
        sha256 = hashlib.sha256()
        with output.open('wb') as stream:
            for part in file['FileChunkParts']:
                with (CACHE / part['Guid']).open('rb') as chunk:
                    chunk.seek(number(part['Offset']))
                    data = chunk.read(number(part['Size']))
                if len(data) != number(part['Size']):
                    raise RuntimeError('Incomplete file chunk')
                stream.write(data)
                sha1.update(data)
                sha256.update(data)
        if sha1.digest() != raw_number(file['FileHash']):
            raise RuntimeError('File digest mismatch: ' + str(relative))
        checks.append({'path': str(relative.relative_to('Content')), 'sha256': sha256.hexdigest()})
    local = json.loads((OUT / 'source-files.json').read_text())
    expected = {file['path']: file['sha256'] for file in local['files']}
    if {file['path']: file['sha256'] for file in checks} != expected:
        raise RuntimeError('CDN build does not match the files downloaded by the user.')
    (OUT / 'source-verification.json').write_text(json.dumps({
        'status': 'PASS', 'files': len(checks), 'build': MANIFEST['BuildVersionString'],
        'manifest_sha256': hashlib.sha256((OUT / 'source.manifest').read_bytes()).hexdigest(),
        'matches_user_download': True,
    }, indent=2))
    print('RURAL_SOURCE_VERIFIED', len(checks), flush=True)


if __name__ == '__main__':
    main()
