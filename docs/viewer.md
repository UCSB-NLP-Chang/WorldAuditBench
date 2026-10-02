# Interactive environment viewer

The viewer is a single-user tool for browsing the 213 benchmark tasks and playing
their environments. It has environment/taxonomy filters, scene instructions,
optional anomaly answers, reset, stop and full-screen controls. It does not need
the private human-annotation services, identities, ratings or databases.

## Three.js on your computer

After installing the repository's Python requirements:

```bash
python scripts/view_task.py JS_AF01 --download
```

Select a task and click **Open environment**. The environment package downloads
on first use; verified downloads are reused. Three.js renders inside the browser.
Click the scene to capture the mouse; use WASD and mouse to explore, and Esc to
release the pointer. Instructions may describe additional scene-specific keys.

The rubric is hidden by default. **Show anomaly and rubric** reveals the answer.
Selecting another task changes the description; **Open environment** switches
the running scene. **Reset environment** starts that task again, and **Stop**
releases its runtime. The label below the scene always identifies the active task.

In Unreal, reaching the task perimeter displays **Task boundary reached** over
the player, including in full screen. It disappears when you move away. The viewer
reads the running game's native boundary events, so the warning works while the
engine HUD and minimap are hidden. It does not change the task's movement limits.

## Unreal on a Linux NVIDIA GPU host

Install the repository's Python requirements, Node.js 22+ and npm on the host.
Then build Epic's UE 5.6 infrastructure once:

```bash
python scripts/setup_pixel_streaming.py
python scripts/view_task.py S01 --download --no-browser --port 19100 --gpu 0
```

The setup script checks out EpicGamesExt/PixelStreamingInfrastructure at
`8cbcbb2ce8d322f23231e0c89c7cd35ab0edb5f9`, builds its signalling server and
reference player, and limits their HTTP/WebSocket listeners to loopback. The
dependency stays under ignored `out/pixel-streaming/`; its MIT license stays in
that checkout. Existing checkouts at a different revision are not overwritten.

Each Unreal session starts its own signalling server and packaged game. The
viewer verifies the executable against its launch profile, preserves the task's
map and exploration policy, and uses the interactive Pixel Streaming input path.
Video targets 1280×720 at 30 FPS with a 3 Mbps maximum bitrate. Actual video
delivery depends on the client and network. This path does not pause the game
after every action. The agent's separate HTTP observation API remains available
through `scripts/serve_unreal.py` for benchmark runs.

## Connect from your laptop

Run the viewer on the GPU host with `--no-browser`. From your laptop:

```bash
ssh -N -L 19100:127.0.0.1:19100 USER@GPU_HOST
```

Open **http://127.0.0.1:19100/**. You can use a different local port, for example
`-L 19200:127.0.0.1:19100`, and open `http://127.0.0.1:19200/` instead. The viewer
proxies the player and signalling WebSocket through this same origin, so no
separate player-port tunnel or hardcoded AWS address is needed.

**SSH forwards the page and signalling, not WebRTC video.** For a cloud GPU with
private network addresses, configure reachable STUN/TURN infrastructure and the
corresponding firewall rules. A TURN relay is needed when a direct media path is
unavailable. Put the RTC configuration in an ignored private file on the GPU host:

```json
{
  "iceServers": [
    {"urls": ["stun:YOUR_RELAY_HOST:3478"]},
    {
      "urls": ["turn:YOUR_RELAY_HOST:3478?transport=udp", "turn:YOUR_RELAY_HOST:3478?transport=tcp"],
      "username": "YOUR_TURN_USERNAME",
      "credential": "YOUR_TURN_PASSWORD"
    }
  ]
}
```

```bash
python scripts/view_task.py S01 --download --no-browser \
  --ice-config .private/viewer-ice.json
```

These are placeholders for your relay; the repository does not provision TURN
or contain the project's private credentials. Configuration is passed to Epic's
signalling server for WebRTC negotiation. If the player connects but video never
starts, check TURN reachability/credentials and the GPU host's media networking.

## Runtime options

| Option | Purpose |
| --- | --- |
| `--runtime-root PATH` | Downloaded environments and generated launch profiles |
| `--pixel-streaming-root PATH` | Built UE 5.6 infrastructure checkout |
| `--unreal-profiles PATH` | Reuse existing launch profiles, with executable hash verification |
| `--node PATH` | Node.js executable for signalling and readiness checks |
| `--gpu N` | Unreal graphics adapter index |
| `--ice-config PATH` | Private WebRTC STUN/TURN configuration |
| `--dataset PATH` | Existing task parquet file |
| `--port N` | Loopback viewer port; default 19100 |

Use `--unreal-profiles` only with trusted profiles that follow the schema emitted
by `scripts/download_resources.py`; profiles specify local executables and their
arguments. Normal `--download` setup generates these profiles automatically.

The viewer owns one active environment. Reset, switching and stopping close its
previous game and signalling processes. Closing the server also cleans them up.
Closing a browser tab leaves the server running; use **Stop** or terminate the
server to release GPU resources. Multiple tabs share the same session. For
independent users, run separate viewers with distinct ports and appropriate GPU
capacity. The server binds to loopback and is intended for local use or SSH
forwarding; exposing a shared public service requires access control and resource
management outside this viewer.

Startup logs are under `out/viewer/stream-*/`. A Mac can browse Unreal task details
but must connect to a viewer on a Linux GPU host to play them.
