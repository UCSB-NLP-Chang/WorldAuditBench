#!/bin/bash
# GPU 6: the 4B follows the 8B (run_house_f2_model.sh qwen8b) on the same card.
cd "$(dirname "$0")/.."
until grep -q "qwen8b DONE" runs/house-f2-all.log; do sleep 60; done
bash scripts/run_house_f2_model.sh qwen4b "Qwen/Qwen3-VL-4B-Instruct" 6 8021 0.90 6
