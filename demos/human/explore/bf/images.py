"""Validate bounded PNG uploads without trusting filenames or MIME alone."""
import base64
import struct
import zlib
from .common import require, digest


def decode_png(encoded):
    require(isinstance(encoded, str) and len(encoded) <= 7 * 1024 * 1024, '截图过大')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError:
        require(False, '截图编码无效')
    validate_png(raw)
    return raw


def validate_png(raw):
    require(0 < len(raw) <= 5 * 1024 * 1024 and raw.startswith(b'\x89PNG\r\n\x1a\n'), '仅支持 PNG 截图（最多 5 MiB）')
    offset, chunks, compressed = 8, [], bytearray()
    while offset + 12 <= len(raw):
        size = struct.unpack('>I', raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        data = raw[offset + 8:offset + 8 + size]
        require(offset + 12 + size <= len(raw), 'PNG 不完整')
        crc = struct.unpack('>I', raw[offset + 8 + size:offset + 12 + size])[0]
        require(zlib.crc32(kind + data) & 0xffffffff == crc, 'PNG 校验失败')
        chunks.append(kind)
        if kind == b'IHDR':
            require(len(chunks) == 1 and len(data) == 13, 'Invalid PNG header')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            require(1 <= width <= 4096 and 1 <= height <= 2160 and depth == 8 and color in (2, 6) and compression == filtering == interlace == 0, '不支持的截图格式')
        if kind == b'IDAT':
            compressed.extend(data)
        offset += size + 12
        if kind == b'IEND':
            break
    require(chunks and chunks[0] == b'IHDR' and chunks[-1] == b'IEND' and offset == len(raw) and compressed, 'PNG 不完整')
    expected = height * (1 + width * (3 if color == 2 else 4))
    try:
        inflater = zlib.decompressobj()
        pixels = inflater.decompress(compressed, expected + 1)
        require(len(pixels) == expected and inflater.eof and not inflater.unused_data, 'PNG 像素数据无效')
    except zlib.error:
        require(False, 'PNG 解码失败')
    return {'size': len(raw), 'sha256': digest(raw), 'mime': 'image/png'}
