# Download and run the environments

Compiled Linux x86_64 Unreal packages and the six standalone Three.js builds are
published on [Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench-runtime).
The residential build is reused from the
[demo runtime repository](https://huggingface.co/datasets/ziyjiang/WorldAuditBench-demo-runtime).
The release covers the 126 Unreal and 87 Three.js tasks in the paper split.
Editable third-party scene projects and original model/texture assets are outside
this release's scope.

## Install

Run from the source repository with Python 3.11+. List package sizes before downloading:

```bash
python scripts/download_resources.py --list
python scripts/download_resources.py --package indoor --package icl-examples
```

The complete download is about **14.9 GB**, including the residential package.
Omit `--package` to install all released packages. Repeat it to select several.
The installer pins each download to a Hugging Face commit, verifies the archive
SHA-256 and executable SHA-256, and generates local profiles under `out/runtime/`.
It deletes its downloaded archive after successful extraction; use `--keep-archives`
to keep it. Keep enough free disk space for the archive and extracted environment.
`--root /path/to/runtime` selects another installation directory.

ICL installation restores the 29 images under `examples/icl/images/` and the
recorded copies needed by the human-service code. No model credentials are needed
for resource downloads.

## Run an Unreal task

Use a Linux x86_64 GPU host with NVIDIA drivers, Vulkan and the runtime libraries
needed by Unreal Engine 5.6. The published packages have been tested on A10G and
the residential demo on HF T4. A CPU-only machine cannot render these environments.

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
python scripts/native-agents/launch.py gemini \
  --environment unreal-http --env-url http://127.0.0.1:19100 \
  --task H01 --model gemini-3.8-flash --gemini-thinking medium \
  --max-actions 40 --max-tool-calls 400 --require-full-budget \
  --observation on-demand --run-dir out/runs/gemini-H01
```

For a remote GPU host, forward the server's loopback port with SSH and use the
forwarded local URL. No public server port is required. Urban uses one download
(`--package urban`) containing the four cooked scene builds needed by its 15 tasks.
The IPC-fixed experiment executables and cooked files are preserved byte for byte. The installer merges those profiles with the other Unreal task profiles and remaps the exploration policies automatically.

## Run a Three.js task

```bash
python scripts/download_resources.py --package threejs-builds --package icl-examples
python scripts/native-agents/launch.py gemini \
  --environment threejs --task JS_AF01 --seed 5 \
  --browser-config out/runtime/browser-profiles/JS_AF01.json \
  --model gemini-3.8-flash --gemini-thinking medium \
  --max-actions 40 --max-tool-calls 400 --require-full-budget \
  --observation on-demand --run-dir out/runs/gemini-JS_AF01
```

Install the browser and native-client dependencies described in
[native-agent-mcp.md](native-agent-mcp.md). The installer verifies all six page
hashes and creates a configuration for each of the 87 paper tasks. These configs
contain only the browser launch fields, not the task answers.

## Visual validation

Task identity, expanded bounds and HUD checks are recorded in the
[October 2 validation report](validation/2026-10-02/README.md). Visual acceptance
remains open for the listed scene issues; the runtime download is not a claim
that every native scene defect has been removed.

## Release boundaries

| Resource | Status |
|---|---|
| Compiled Unreal Linux environments | Published; 8 downloads, 126 paper tasks |
| Six built Three.js environments | Published; 87 paper tasks |
| 29 ICL demonstration images | Published, with SHA-256 checks |
| Editable Unreal scene assets | Not distributed |
| Open-P2P 1.2B weights | Use upstream distribution and license; setup guide pending |
| Original VLA recordings and frozen ablation inputs | Pending |

`resources/releases.json` is the installer manifest. `resources/manifest.json`
retains the per-file identities and remaining optional resources. Model access,
VLA checkpoint setup and unpublished original experiment outputs are separate
from installing the runnable environments. Third-party terms and attribution
remain applicable; see [THIRD_PARTY.md](../THIRD_PARTY.md).

The resource and source checks are:

```bash
python scripts/check_release.py
python scripts/check_release.py --resources
```

The second check requires all published packages installed at the default root
(or the directory passed with `--runtime-root`). It does not require resources
marked pending or excluded from the release. These checks do not reproduce the
paper's model scores.
