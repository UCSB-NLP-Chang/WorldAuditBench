"""Open-P2P inference server over stdin/stdout JSONL (single client, sequential).

Runs INSIDE the open-p2p uv environment:
  CUDA_VISIBLE_DEVICES=3 uv run --project /mnt/data3/jingbo/open-p2p \
      python harness/p2p_server.py --config <yaml> --checkpoint <ckpt> [--eager]

Protocol (one JSON per line on stdin):
  {"img": "<b64 jpeg>", "text": "..."}   -> "#ACT {keys, buttons, dx, dy}" on stdout
  {"cmd": "reset"}                        -> "#OK reset"
  {"cmd": "quit"}                         -> exits
Startup prints "#READY" when the model is loaded. All logging goes to stderr.
"""
import argparse
import os
import base64
import io
import json
import sys
import types
import logging

# elefant_rust is only used by the training dataloader; stub it out for inference
rust_stub = types.ModuleType("elefant_rust")
rust_stub.video_proto_dataset = types.SimpleNamespace(ShuffleThread=None)
rust_stub.zmq_queue = types.SimpleNamespace()   # training-only IPC, never called at inference
sys.modules["elefant_rust"] = rust_stub

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402

from elefant.config import load_config  # noqa: E402
from elefant.policy_model.config import LightningPolicyConfig  # noqa: E402
from elefant.policy_model.stage3_finetune import Stage3LabelledBCLightning  # noqa: E402
from elefant.data.action_mapping import UniversalAutoregressiveActionMapping  # noqa: E402
from elefant.policy_model import inference as p2p_inference  # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, force=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--eager", action="store_true", help="disable torch.compile")
    ap.add_argument("--precision", default=None, help="override config.shared.precision (e.g. bf16-true: half the GPU memory, faster on tensor cores)")
    args = ap.parse_args()

    if args.eager:
        torch.compiler.set_stance("force_eager")
    if os.environ.get("P2P_MEM_FRACTION"):   # cap the caching allocator so several servers can share one GPU
        torch.cuda.set_per_process_memory_fraction(float(os.environ["P2P_MEM_FRACTION"]), 0)
        logging.info("gpu memory fraction cap: %s", os.environ["P2P_MEM_FRACTION"])

    config = load_config(args.config, LightningPolicyConfig)
    if args.precision:
        config.shared.precision = args.precision
        logging.info("precision override: %s", args.precision)
    action_mapping = UniversalAutoregressiveActionMapping(config=config.shared.action_mapping)

    logging.info("loading checkpoint %s", args.checkpoint)
    # construct directly on GPU with the right precision (flex-attention block masks are
    # built at module init and do not follow a later .to())
    import lightning as pl
    dummy_trainer = pl.Trainer(precision=config.shared.precision, accelerator="gpu", devices=[0])
    with dummy_trainer.init_module():
        # checkpoints/<size>/slim-*.ckpt (state_dict only, written by harness/p2p_slim_ckpt.py) is preferred by
        # vla_explore._find_ckpt: loading the full 15 GB training checkpoint onto the GPU peaked above 12 GB and left no
        # room for a second server on the same card
        model = Stage3LabelledBCLightning.load_from_checkpoint(
            args.checkpoint, config=config, inference_mode=True, map_location="cpu")
    model = model.to("cuda")   # host-RAM load (peak = weights only), then onto the GPU; the KV cache / rope caches are (re)built on the device below
    model.eval()

    state = p2p_inference.KVCacheInferenceState(config, action_mapping, model)

    with torch.inference_mode():
        # warmup (fills kv cache once so any lazy init/compile happens now)
        for _ in range(3):
            dummy = torch.randint(0, 255, (3, 192, 192), dtype=torch.uint8, device="cuda")
            state.get_action(dummy, None)
        state.reset()
    torch.cuda.empty_cache()   # release the allocator's warmup blocks: several servers share one GPU
    logging.info("gpu memory after warmup: allocated %.2f GB, reserved %.2f GB", torch.cuda.memory_allocated() / 1e9, torch.cuda.memory_reserved() / 1e9)

    print("#READY", flush=True)

    n_acts = 0
    with torch.inference_mode():
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            if req.get("cmd") == "quit":
                break
            if req.get("cmd") == "reset":
                state.reset()
                print("#OK reset", flush=True)
                continue
            img = Image.open(io.BytesIO(base64.b64decode(req["img"]))).convert("RGB")
            if img.size != (192, 192):
                img = img.resize((192, 192), Image.BILINEAR)
            arr = np.asarray(img, dtype=np.uint8)                    # HWC
            frame = torch.from_numpy(arr).permute(2, 0, 1).to("cuda")  # CHW uint8
            action = state.get_action(frame, req.get("text"))
            n_acts += 1
            if n_acts % 20 == 0:
                torch.cuda.empty_cache()   # keep the reserved pool close to the live set (several servers share the GPU)
            print("#ACT " + json.dumps({
                "keys": list(action.keys),
                "buttons": list(action.mouse_buttons),
                "dx": int(action.mouse_delta_x),
                "dy": int(action.mouse_delta_y),
            }), flush=True)


if __name__ == "__main__":
    main()
