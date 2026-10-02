"""Write a state_dict-only copy of an Open-P2P Lightning checkpoint (drops optimizer / scheduler / loop state):
15.6 GB -> 5.3 GB for the 1.2B model, so loading it onto the GPU peaks far lower and several servers fit on one card.
Usage (inside the open-p2p venv): python agent/vla/p2p_slim_ckpt.py checkpoints/1200M/checkpoint-step=00500000.ckpt
Writes checkpoints/1200M/slim-<name>.ckpt, which vla_explore._find_ckpt picks up (sorted last)."""
import sys, pathlib, torch
src = pathlib.Path(sys.argv[1]); dst = src.with_name('slim-' + src.name.replace('=', '-'))
ck = torch.load(src, map_location='cpu', weights_only=False)
slim = {k: ck[k] for k in ('epoch', 'global_step', 'pytorch-lightning_version', 'hyper_parameters') if k in ck}
slim['state_dict'] = ck['state_dict']
torch.save(slim, dst)
print(dst, round(dst.stat().st_size / 1e9, 2), 'GB')
