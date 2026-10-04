# Download and run the environments

Compiled Linux x86_64 Unreal packages and the six standalone Three.js builds are
published on [Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench).
Each Unreal environment has one archive under `unreal/`; Subway includes the
concourse, and Urban includes its four scene versions.
The release covers the 126 Unreal and 87 Three.js tasks in the paper split.
Editable third-party scene projects and original model/texture assets are outside
this release's scope.

## Install

Run from the source repository with Python 3.11+. List package sizes before downloading:

```bash
python scripts/download_resources.py --list
python scripts/download_dataset.py
python scripts/download_resources.py --package indoor
```

The complete download is about **16.1 GB**, including the shared ICL images.
Omit `--package` to install all released packages. Repeat it to select several.
The installer pins each download to a Hugging Face commit, verifies the archive
SHA-256 and executable SHA-256, and generates local profiles under `out/runtime/`.
It deletes its downloaded archive after successful extraction; use `--keep-archives`
to keep it. Keep enough free disk space for the archive and extracted environment.
`--root /path/to/runtime` selects another installation directory.

`download_dataset.py` caches the unified task table and shared demonstrations under
`out/dataset/`. Native launchers read this cache by default. The optional
`--package icl-examples` resource entry restores the archival image layout for
older human-service tools. No model credentials are needed for downloads.

## Run an Unreal task

Use a Linux x86_64 GPU host with NVIDIA drivers, Vulkan and the runtime libraries
needed by Unreal Engine 5.6. The published packages have been tested on A10G.
A CPU-only machine cannot render these environments.

```bash
python scripts/serve_unreal.py --task H01 --gpu 0 --port 19100
```

The server verifies the executable before launching it, listens on loopback, and
uses a private state directory for each episode. Choose an available GPU. Use
`--profiles /path/to/runtime/unreal-profiles.json` after installing to a custom root.
The launcher disables the Unreal HUD before the first observation, including the
minimap and its background. It leaves the scene pixels intact. Use this launcher
rather than starting a packaged executable without its task and exploration arguments.
All 126 Unreal task profiles retain the frozen exploration bounds with 3× the
original horizontal area. Stop the server and start a fresh one for each episode.

In another terminal, connect an authenticated native model client:

```bash
python agent/vlm/native/launch.py gemini \
  --environment unreal-http --env-url http://127.0.0.1:19100 \
  --task H01 --model gemini-3.8-flash --gemini-thinking medium \
  --max-actions 40 --max-tool-calls 400 --require-full-budget \
  --observation on-demand --run-dir out/runs/gemini-H01
```

For a remote GPU host, forward the server's loopback port with SSH and use the
forwarded local URL. No public server port is required. Urban uses one download
(`--package urban`) containing the four cooked scene builds needed by its 15 tasks.
The installer reads each package's verified launch settings and generates the
task profiles automatically.

## Run a Three.js task

```bash
python scripts/download_dataset.py
python scripts/download_resources.py --package threejs-airfield
python agent/vlm/native/launch.py gemini \
  --environment threejs --task JS_AF01 --seed 5 \
  --browser-config out/runtime/browser-profiles/JS_AF01.json \
  --model gemini-3.8-flash --gemini-thinking medium \
  --max-actions 40 --max-tool-calls 400 --require-full-budget \
  --observation on-demand --run-dir out/runs/gemini-JS_AF01
```

Install the browser and native-client dependencies described in
[native-agent-mcp.md](native-agent-mcp.md). The installer verifies all six page
hashes and creates a configuration for each task in the selected environment. Use
`--package threejs-builds` to install all six environments, or select
`threejs-airfield`, `threejs-cottage`, `threejs-house`, `threejs-reef`,
`threejs-sponza` and `threejs-wilderness` individually. These configs
contain only the browser launch fields, not the task answers.

## Release boundaries

| Resource | Status |
|---|---|
| Compiled Unreal Linux environments | Published; 7 downloads, 126 paper tasks |
| Six built Three.js environments | Published; 87 paper tasks |
| 29 ICL demonstration images | Published, with SHA-256 checks |
| Editable Unreal scene assets | Not distributed |
| Open-P2P 1.2B weights | Use upstream distribution and license; setup guide pending |
| Original VLA recordings and frozen ablation inputs | Pending |

`data/resources/releases.json` is the installer manifest. `data/resources/manifest.json`
retains the per-file identities and remaining optional resources. Model access,
VLA checkpoint setup and unpublished original experiment outputs are separate
from installing the runnable environments. Third-party terms and attribution
remain in the accompanying environment files.

The resource and source checks are:

```bash
python scripts/check_release.py
python scripts/check_release.py --resources
```

The second check requires all published packages installed at the default root
(or the directory passed with `--runtime-root`). It does not require resources
marked pending or excluded from the release. These checks do not reproduce the
paper's model scores.
