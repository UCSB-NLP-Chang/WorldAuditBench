#!/bin/bash
# Mirror all frontend dependencies and 3D assets into assets/; afterwards the env needs no network.
# Idempotent: existing non-empty files are skipped.
set -e
cd "$(dirname "$0")/.."
A=assets

get() { # get <url> <dest>
  if [ -s "$2" ]; then echo "skip  $2"; return; fi
  mkdir -p "$(dirname "$2")"
  echo "fetch $2"
  curl -fsSL --retry 3 --max-time 300 "$1" -o "$2.part" && mv "$2.part" "$2"
}

THREE=https://unpkg.com/three@0.169.0
get $THREE/build/three.module.js                      $A/vendor/three/three.module.js
get $THREE/examples/jsm/loaders/GLTFLoader.js         $A/vendor/three/addons/loaders/GLTFLoader.js
get $THREE/examples/jsm/loaders/DRACOLoader.js        $A/vendor/three/addons/loaders/DRACOLoader.js
get $THREE/examples/jsm/environments/RoomEnvironment.js $A/vendor/three/addons/environments/RoomEnvironment.js
get $THREE/examples/jsm/utils/BufferGeometryUtils.js  $A/vendor/three/addons/utils/BufferGeometryUtils.js
get $THREE/examples/jsm/loaders/RGBELoader.js         $A/vendor/three/addons/loaders/RGBELoader.js
get $THREE/examples/jsm/geometries/RoundedBoxGeometry.js $A/vendor/three/addons/geometries/RoundedBoxGeometry.js
get https://unpkg.com/three-mesh-bvh@0.7.8/build/index.module.js $A/vendor/three-mesh-bvh/index.module.js

DR=https://www.gstatic.com/draco/versioned/decoders/1.5.7
get $DR/draco_wasm_wrapper.js $A/vendor/draco/draco_wasm_wrapper.js
get $DR/draco_decoder.wasm    $A/vendor/draco/draco_decoder.wasm
get $DR/draco_decoder.js      $A/vendor/draco/draco_decoder.js

# Sponza (multi-file glTF: parse uris from the .gltf and fetch each)
SP=https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/Sponza/glTF
get $SP/Sponza.gltf $A/sponza/Sponza.gltf
python3 - "$A/sponza" "$SP" <<'EOF'
import json, sys, subprocess, os
d, base = sys.argv[1], sys.argv[2]
g = json.load(open(f"{d}/Sponza.gltf"))
uris = [b["uri"] for b in g.get("buffers", []) if "uri" in b]
uris += [i["uri"] for i in g.get("images", []) if "uri" in i]
for u in uris:
    dest = os.path.join(d, u)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print("skip ", dest); continue
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print("fetch", dest)
    subprocess.run(["curl", "-fsSL", "--retry", "3", f"{base}/{u}", "-o", dest], check=True)
EOF

get https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/models/gltf/dungeon_warkarma.glb $A/dungeon/dungeon_warkarma.glb

echo "== done =="
du -sh $A/* 2>/dev/null
