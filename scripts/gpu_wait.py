#!/usr/bin/env python3
"""Block until N GPUs each have at least FREE_GB free (other users' jobs come and go on this
shared machine), then print the chosen GPU indices (comma-separated) and exit 0.

usage: gpu_wait.py --n 2 --free-gb 44 [--timeout-h 10] [--poll 120] [--prefer 4,6,3,0,1,2]
"""
import argparse
import subprocess
import sys
import time


def free_gpus(free_gb):
    out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
    ok = []
    for line in out.strip().splitlines():
        i, used, total = [int(v) for v in line.split(",")]
        if (total - used) / 1024 >= free_gb:
            ok.append(i)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--free-gb", type=float, default=44)
    ap.add_argument("--timeout-h", type=float, default=12)
    ap.add_argument("--poll", type=int, default=120)
    ap.add_argument("--prefer", default="4,6,3,2,1,0,5")
    a = ap.parse_args()
    prefer = [int(v) for v in a.prefer.split(",")]
    t0 = time.time()
    while time.time() - t0 < a.timeout_h * 3600:
        ok = free_gpus(a.free_gb)
        pick = [g for g in prefer if g in ok][:a.n]
        if len(pick) >= a.n:
            # confirm twice (a job may be starting up)
            time.sleep(20)
            ok2 = free_gpus(a.free_gb)
            if all(g in ok2 for g in pick):
                print(",".join(str(g) for g in pick))
                return 0
        print(time.strftime("%F %T"), f"waiting: free={ok} need {a.n} x {a.free_gb}GB", file=sys.stderr, flush=True)
        time.sleep(a.poll)
    print("timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
