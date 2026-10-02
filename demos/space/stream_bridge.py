"""Local Pixel Streaming peer, with bounded H.264/JPEG frames over the Space WebSocket."""
import asyncio
import io
import json
import logging
import re
import struct
import time
from fractions import Fraction

import av

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
from websockets.asyncio.client import connect

log = logging.getLogger('worldauditbench.stream')
KEYS = {16, 32, 65, 68, 69, 83, 87}
INPUT_LENGTHS = {60: 3, 61: 2, 70: 1, 71: 1, 72: 6, 73: 6, 74: 9, 75: 7}


def valid_input(data):
    if not data or INPUT_LENGTHS.get(data[0]) != len(data):
        return False
    if data[0] in (60, 61) and data[1] not in KEYS:
        return False
    if data[0] in (72, 73) and data[1] > 2:
        return False
    return True


def jpeg(frame):
    output = io.BytesIO()
    frame.to_image().save(output, format='JPEG', quality=88, subsampling=0)
    return output.getvalue()


class H264Encoder:
    def __init__(self, width, height):
        self.codec=av.CodecContext.create('h264_nvenc','w')
        self.codec.width=width;self.codec.height=height
        self.codec.pix_fmt='yuv420p';self.codec.time_base=Fraction(1,1000000)
        self.codec.framerate=Fraction(30,1);self.codec.bit_rate=5000000;self.codec.gop_size=60
        self.codec.options={'preset':'p1','tune':'ull','profile':'baseline','bf':'0',
                            'rc':'cbr','zerolatency':'1','delay':'0','rc-lookahead':'0'}
        self.codec.open()

    def encode(self, frame, timestamp):
        frame=frame.reformat(format='yuv420p')
        frame.pts=timestamp;frame.time_base=Fraction(1,1000000)
        return [(bytes(p),p.is_keyframe,int(p.pts)) for p in self.codec.encode(frame)]


class StreamBridge:
    def __init__(self):
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.channel = None
        self.latest = None
        self.updated = asyncio.Event()
        self.credits = asyncio.Semaphore(2)
        self.inflight = set()
        self.readers = []
        self.pressed = set()
        self.frames = 0
        self.started = time.monotonic()
        self.format_ready = asyncio.Event()
        self.format = 'jpeg'
        self.encoder = None

        @self.pc.on('datachannel')
        def channel_ready(channel):
            self.channel = channel

            def begin():
                for packet in (b'\x01', b'\x04', b'\x00', b'\x46'):
                    channel.send(packet)

            channel.on('open', begin)
            if channel.readyState == 'open':
                begin()

        @self.pc.on('track')
        def track_ready(track):
            async def consume():
                while True:
                    frame = await track.recv()
                    if track.kind == 'video':
                        self.latest = frame
                        self.updated.set()
            self.readers.append(asyncio.create_task(consume()))

    async def signal(self):
        async with connect('ws://127.0.0.1:8889', max_size=2**20) as ws:
            async for raw in ws:
                message = json.loads(raw)
                kind = message.get('type')
                if kind == 'config':
                    await ws.send(json.dumps({'type': 'subscribe', 'streamerId': 'DefaultStreamer'}))
                elif kind == 'offer':
                    await self.pc.setRemoteDescription(RTCSessionDescription(sdp=message['sdp'], type='offer'))
                    await self.pc.setLocalDescription(await self.pc.createAnswer())
                    await ws.send(json.dumps({'type': 'answer', 'sdp': self.pc.localDescription.sdp}))
                elif kind == 'iceCandidate':
                    value = message.get('candidate')
                    if value and value.get('candidate'):
                        candidate = candidate_from_sdp(value['candidate'].removeprefix('candidate:'))
                        candidate.sdpMid = value.get('sdpMid')
                        candidate.sdpMLineIndex = value.get('sdpMLineIndex')
                        await self.pc.addIceCandidate(candidate)
                elif kind == 'ping':
                    await ws.send(json.dumps({'type': 'pong', 'time': message.get('time')}))
                elif kind in ('disconnectPlayer', 'subscribeFailed'):
                    raise ConnectionError('Local Unreal peer disconnected')

    async def send_frames(self, ws):
        try:await asyncio.wait_for(self.format_ready.wait(),3)
        except asyncio.TimeoutError:pass
        configured=False
        while True:
            await asyncio.wait_for(self.updated.wait(), 30)
            self.updated.clear()
            frame=self.latest
            timestamp=int((time.monotonic()-self.started)*1000000)
            if self.format=='h264':
                try:
                    if not self.encoder:self.encoder=await asyncio.to_thread(H264Encoder,frame.width,frame.height)
                    packets=await asyncio.to_thread(self.encoder.encode,frame,timestamp)
                except Exception as exc:
                    print(f'H264 bridge unavailable, using JPEG: {type(exc).__name__}',flush=True)
                    self.format='jpeg';configured=False;self.encoder=None
                    continue
            else:
                packets=[(await asyncio.to_thread(jpeg,frame),False,timestamp)]
            for encoded,keyframe,pts in packets:
                if not configured:
                    codec='jpeg'
                    if self.format=='h264':
                        sps=re.search(b'\x00\x00(?:\x00)?\x01\x67(.{3})',encoded,re.DOTALL)
                        if not sps:continue
                        codec='avc1.'+sps.group(1).hex().upper()
                    await ws.send_json({'type':'codec','codec':codec,'width':frame.width,'height':frame.height})
                    configured=True
                await asyncio.wait_for(self.credits.acquire(),20)
                self.frames+=1;self.inflight.add(self.frames)
                kind=(1 if keyframe else 2) if self.format=='h264' else 0
                await ws.send_bytes(struct.pack('!IBQ',self.frames,kind,pts)+encoded)
            await asyncio.sleep(1/30 if self.format=='h264' else .05)

    async def receive_input(self, ws):
        count = 0
        window = time.monotonic()
        while True:
            message = await ws.receive()
            if message['type'] == 'websocket.disconnect':
                return
            data = message.get('bytes')
            if data is not None:
                now = time.monotonic()
                if now - window > 1:
                    count = 0
                    window = now
                count += 1
                if count > 240 or not valid_input(data):
                    continue
                if self.channel and self.channel.readyState == 'open':
                    self.channel.send(data)
                    if data[0] == 60:
                        self.pressed.add(data[1])
                    elif data[0] == 61:
                        self.pressed.discard(data[1])
            elif message.get('text') and len(message['text']) < 80:
                try:
                    value=json.loads(message['text'])
                    if not self.format_ready.is_set() and value.get('video') in ('jpeg','h264'):
                        self.format=value['video'];self.format_ready.set()
                    ack = value.get('ack')
                    if isinstance(ack, int) and ack in self.inflight:
                        self.inflight.remove(ack)
                        self.credits.release()
                except (ValueError, AttributeError, TypeError):
                    pass

    async def close(self):
        if self.channel and self.channel.readyState == 'open':
            for key in self.pressed:
                self.channel.send(bytes((61, key)))
            self.channel.send(b'\x47')
        for reader in self.readers:
            reader.cancel()
        await asyncio.gather(*self.readers, return_exceptions=True)
        await self.pc.close()
        self.encoder=None
        print(f'Video bridge closed: {self.format}, {self.frames} frames in {time.monotonic()-self.started:.1f}s', flush=True)
