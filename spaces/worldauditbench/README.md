---
title: WorldAuditBench
emoji: 🌍
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
short_description: Explore Unreal worlds and discover five anomaly families.
pinned: false
---

# WorldAuditBench · Interactive exploration

Explore a furnished Unreal Engine home with keyboard and mouse. Five challenges
cover the benchmark's five anomaly families. Each challenge has one authored bug;
the explanation remains hidden until you choose to reveal it.

[Paper](https://arxiv.org/pdf/2609.40325) ·
[Project](https://ucsb-nlp-chang.github.io/WorldAuditBench/) ·
[Code](https://github.com/UCSB-NLP-Chang/WorldAuditBench)

## Controls

Click the scene to control the camera. Use **WASD** to move, **mouse** to look,
**E** to interact with supported objects, and **Esc** to release the cursor.
Select another challenge to end the current session and return to the scene menu.
One visitor controls the environment at a time; other visitors queue. Sessions
last up to ten minutes and disconnected sessions release their slot after 45 seconds.

## Deployment

This is a Docker Space with a Gradio interface. Unreal, Epic's UE 5.6 Pixel
Streaming signalling library, and a local video receiver run in one container.
The browser receives full-resolution H.264 video and sends keyboard/mouse input
through an authenticated WebSocket on port 7860. The local receiver uses WebRTC
inside the container, so public UDP ports and an external TURN server are not
required. NVENC compresses the video, and browsers with WebCodecs decode it.
Browsers without H.264 support receive JPEG frames instead. Video is capped at
30 frames per second (20 for JPEG), with at most two frames awaiting browser
acknowledgment; slow connections reduce the frame rate instead of building a queue.
This transport is silent. Vulkan and NVENC access are checked before exploration
is enabled, and each scene must report that the selected challenge has loaded.

For a host with a working public WebRTC route, `WAB_TRANSPORT=webrtc` enables the
original video/audio player. Set `WAB_ICE_CONFIG` (JSON RTCConfiguration) if that
deployment requires TURN. The default WebSocket transport ignores this setting.

The app starts with exploration disabled if the runtime is missing or preflight
fails. It never substitutes a video or simulated game for the live environment.

The default deployment downloads the pinned environment during the Docker build
and stores its extracted files in the image. Starting a container reuses those
files; it does not download or unpack the archive again. A newly scheduled
machine may still need to pull the Docker image before it can start.

The public [runtime repository](https://huggingface.co/datasets/ziyjiang/WorldAuditBench-demo-runtime)
contains the archive. `assets.json` pins its commit and SHA-256. The demo archive
excludes development symbols and saved runtime state. No access token is needed.

For another deployment, these environment variables override the asset source
during the build (or at startup when no restored runtime is present):

- `WAB_ASSET_REPO`: HF dataset containing the runtime archive.
- `WAB_ASSET_REVISION`: exact 40-character dataset commit.
- `WAB_ASSET_FILE`: archive filename (default `indoor-demo.tar.gz`).
- `WAB_ARCHIVE_SHA256`: SHA-256 of the complete archive.
- `HF_TOKEN`: read access token, required only for a private asset repository.
- Optional secret `WAB_ICE_CONFIG`: ICE server configuration. Any TURN credentials
  supplied here are sent to connected peers; use short-lived, limited credentials.

The archive contains `release.json` with `binary`, `policy` (relative paths) and
`sha256` (binary digest), the complete Linux runtime package, and its exploration
policy. The full archive and executable are verified before launch.

For an already-restored package, set `WAB_RUNTIME_CONFIG` to a private JSON file
with absolute `binary` and `policy` paths plus the executable's `sha256`.

## Local development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci
npm run build
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 7860 --no-access-log
```

The local UI works without an Unreal package; entering a scene requires a verified
Linux runtime and compatible GPU. Run `python -m unittest test_sessions` for the
queue and lease tests, and `python -m unittest test_app` for API availability and
answer-disclosure checks. `python -m unittest test_stream_bridge` checks stream
authorization, allowed controls, and bounded frame acknowledgments. Real rendering
and mouse input require a GPU browser test.
