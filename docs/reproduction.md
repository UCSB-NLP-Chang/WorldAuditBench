# Experiments

The evaluation set has 213 tasks: 126 Unreal and 87 Three.js.
Task lists are in `data/benchmark/splits/`; inputs and rubrics come from
[Hugging Face](https://huggingface.co/datasets/ziyjiang/WorldAuditBench).

## VLM agents

```bash
python scripts/experiments/run.py --agent gemini \
  --tasks @data/benchmark/splits/unreal.txt --download --output out/gemini-unreal
```

Choose `codex`, `claude`, `gemini`, `qwen` or `muse`. The presets record the paper's
model IDs and medium reasoning settings. Each task starts a fresh environment and
native client. The default budget is 40 actions.

For budget and guidance experiments, use `--max-actions 20` or `--max-actions 60`,
and `--no-icl` to remove demonstrations. Removing the category hint or testing
multiple anomalies requires the corresponding task input and environment setup;
`--no-icl` alone does not reproduce those conditions.

## VLA exploration

VLA exploration requires an Open-P2P installation and its 1.2B checkpoint.
Set `P2P_ROOT` to that checkout and `P2P_PY` to its Python environment. The explorer
uses `config/policy_model/1200M.yaml` and
`checkpoints/1200M/slim-checkpoint-step-00500000.ckpt` within that checkout.

Record 60 simulated seconds (1,200 ticks of 50 ms), saving one frame every 10 ticks:

```bash
python -m agent.vla.vla_explore --tasks JS_AF01 --download \
  --ticks 1200 --dt-ms 50 --record-every 10 --tag vla-threejs

python scripts/download_resources.py --package subway
python -m agent.vla.vla_ue --tasks S01 \
  --profiles out/runtime/unreal-profiles.json \
  --ticks 1200 --dt-ms 50 --record-every 10 --tag vla-unreal
```

Recordings are written under `runs/<tag>/<task>/`.
The VLM then analyzes these recordings:

```bash
python agent/vla/replay.py --recordings runs/vla-threejs \
  --batch out/vla-gemini --tasks JS_AF01 --client gemini \
  --model gemini-3.8-flash --replay-mode vqa --max-actions 0 --stage all
```

Use `python agent/vla/replay.py --help` for authentication and judge options.
The paper's single-report setting uses `--replay-mode vqa` and zero exploration
actions during analysis.

## Judge

```bash
python -m judge.judge --task S01 \
  --model-output out/gemini-unreal/S01/report.json \
  --evidence out/gemini-unreal/S01/evidence.json \
  --output out/gemini-unreal/S01/judge.json
```

The formal judge uses GPT-6 Astra with medium reasoning and returns a binary
score plus explanation. Keep the assigned task denominator; unfinished attempts
must remain visible when reporting aggregate results. Authentication or scoring
errors are reported as errors, not fabricated scores.
