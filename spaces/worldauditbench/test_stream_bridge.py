import asyncio
import struct
import unittest
from starlette.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient
from stream_bridge import StreamBridge, valid_input
import app

class StreamSafetyTests(unittest.TestCase):
    def test_only_game_controls_are_forwarded(self):
        self.assertTrue(valid_input(bytes((60,87,0))))
        self.assertTrue(valid_input(struct.pack('<BHHhh',74,32768,32768,20,-20)))
        for packet in (b'',b'\x33command',bytes((60,192,0)),bytes((60,77,0)),b'\x4a',bytes((72,255,0,0,0,0))):
            self.assertFalse(valid_input(packet))

    def test_video_requires_session_ownership(self):
        with TestClient(app.app) as client:
            with self.assertRaises(WebSocketDisconnect) as denied:
                with client.websocket_connect('/api/stream/missing?token=wrong'):
                    pass
            self.assertEqual(denied.exception.code,1008)

class FrameFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_ack_does_not_allow_unbounded_frames(self):
        bridge=StreamBridge()
        await bridge.credits.acquire();await bridge.credits.acquire()
        bridge.inflight.add(1)
        messages=iter([{'type':'websocket.receive','text':'{"ack":1}'},
                       {'type':'websocket.receive','text':'{"ack":1}'},
                       {'type':'websocket.receive','text':'{"ack":999}'},
                       {'type':'websocket.disconnect'}])
        class Socket:
            async def receive(self):return next(messages)
        try:
            await bridge.receive_input(Socket())
            await asyncio.wait_for(bridge.credits.acquire(),0.1)
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(bridge.credits.acquire(),0.01)
        finally:await bridge.close()

if __name__=='__main__':unittest.main()
