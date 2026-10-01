# 交接：用 GPT-6（Codex CLI，medium）跑 "VLM 看 VLA 录像找 bug" 实验

本次 GPT-6 实验的账号使用范围、专用登录和执行计划见 [vla-replay-gpt6-plan.md](vla-replay-gpt6-plan.md)。

面向在另一台机器上执行的 agent。目标：对已经录好的 VLA 探索录像（Unreal 111 + Urban 15 + three.js 87），
用 Codex CLI + `gpt-6-astra`（reasoning medium）做一次性作答审计（`--replay-mode vqa`），再用 GPT-6 二元 judge 打分。
Gemini 3.8 Flash 和 Opus 5 已经在 AWS 上用同一套代码跑完，结果在 AWS 的 `~/vla-results/`；你要产出的是
`gpt-6-astra-medium-vqa`、`gpt-6-astra-medium-vqa-urban`、`gpt-6-astra-medium-vqa-threejs` 三个同格式目录。

## 1. 实验是什么

- 录像：Open-P2P 1.2B 探索器盲走 60 s 模拟时间，每 0.5 s 存一帧（120 帧）+ `poses.jsonl`（每 50 ms 的位置、朝向、按键）+ `meta.json`。
- 审计：native CLI（这里是 Codex）通过 `world_audit` MCP server（`auditor/mcp_agent/server.py`，环境 `vla-replay`）看录像。
  vqa 模式下只有三个工具：`read_example`（该任务子类的一个 ICL 示例，和具身实验相同）→ `observe`（起始帧 a0 + 全部
  120 帧内联 480x288 + 探索者轨迹文本）→ `report(bugs, summary)`（一次性给出全部 bug，写入 ledger 后结束）。
  没有环境动作、没有 inspect/notes/history，每个 episode 正好 3 次工具调用。prompt、场景描述、ICL、judge 输入规则与具身批次一致。
- 打分：`eval/judge.py`（GPT-6 二元 judge：rubric + 最终 ledger + 证据帧截图），由批处理脚本的 judge 阶段自动调用。

设计说明和费用测量见 `docs/native-agent-mcp.md` 的 "VLA recordings" 一节和 `reports/vla-vqa-20260920.md`。

## 2. 机器准备

```bash
git clone <repo> game-auditing && cd game-auditing && git checkout iclr      # 需要 commit 003892f 或更新
python3.12 --version                                                          # 需要 python 3.12
python3.12 scripts/native-agents/setup.py                                     # out/native-agents/venv + pinned 上游 clone (d59b663)
#   如果 setup.py 的 GitHub clone 失败（无凭证），手动：
#   git clone --no-checkout . out/native-agents/game-auditing && git -C out/native-agents/game-auditing checkout --detach d59b663ddb210414bc0cd5ce66cab0f0fd04f76a
#   然后再跑一次 setup.py 装依赖
python3.12 -m venv .venv && .venv/bin/pip install pillow numpy imageio imageio-ffmpeg    # judge 阶段和帧还原用
npm install -g @openai/codex && codex login                                   # ChatGPT 登录；judge 和 agent 都用它
codex login status                                                            # 必须显示 ChatGPT 登录
out/native-agents/venv/bin/python -m pip install pytest && out/native-agents/venv/bin/python -m pytest -q tests/test_vla_replay.py tests/test_native_mcp.py
```

仓库里已经带着：ICL 示例包 `output/icl-unreal-20260916/`（含 29 张图）、任务目录 `scripts/native-agents/task-{scenes,subcategories}.json`、
三个 profile 文件（rubric、子类、场景）`reports/ue-aws-profiles-20260918.json`、`reports/ue-urban-ipc-profiles-20260920.json`、
`reports/threejs-vla-profiles-20260920.json`、Urban 任务列表 `scripts/vla-lists/vla-ue-urban-list.txt`。

## 3. 录像

从 AWS 机器复制（含已还原的帧，共 5.7 GB）：

```bash
rsync -a ec2-user@<aws-host>:~/vla-recordings/vla-ue-v1 ec2-user@<aws-host>:~/vla-recordings/vla-ue-urban-v1 ec2-user@<aws-host>:~/vla-recordings/vla-threejs-v2 ~/vla-recordings/
ln -s ~/vla-recordings runs        # 在仓库根目录；脚本按 runs/<tag> 找录像
```

如果只拿到 `meta.json + poses.jsonl + video.mp4`（没有 f*.jpg），先还原帧：
`.venv/bin/python tools/vla_frames_from_video.py runs/vla-ue-v1 runs/vla-ue-urban-v1 runs/vla-threejs-v2`
（视频 4 fps，一帧视频 = 一帧记录；会写 `frames.restored.json` 标记）。

## 4. 跑 agent + judge

三个批次可以并发（只走 API，不占 GPU）。`--stage all` = agent 阶段结束后自动用 GPT-6 judge 打分。

```bash
cd game-auditing
R=out/native-agents/batches
# Unreal 111
nohup out/native-agents/venv/bin/python scripts/native-agents/run_vla_replay.py --recordings runs/vla-ue-v1 \
  --profiles reports/ue-aws-profiles-20260918.json --batch $R/vla-vqa-ue-codex-$(date +%Y%m%d) --tasks all \
  --replay-mode vqa --client codex --reasoning-effort medium --workers 3 --stage all \
  --judge-model gpt-6-astra --judge-effort medium > $R/vla-vqa-ue-codex.log 2>&1 &
# Urban 15
nohup out/native-agents/venv/bin/python scripts/native-agents/run_vla_replay.py --recordings runs/vla-ue-urban-v1 \
  --profiles reports/ue-urban-ipc-profiles-20260920.json --batch $R/vla-vqa-urban-codex-$(date +%Y%m%d) \
  --tasks @scripts/vla-lists/vla-ue-urban-list.txt --replay-mode vqa --client codex --reasoning-effort medium \
  --workers 3 --stage all --judge-model gpt-6-astra --judge-effort medium > $R/vla-vqa-urban-codex.log 2>&1 &
# three.js 87
nohup out/native-agents/venv/bin/python scripts/native-agents/run_vla_replay.py --recordings runs/vla-threejs-v2 \
  --profiles reports/threejs-vla-profiles-20260920.json --batch $R/vla-vqa-threejs-codex-$(date +%Y%m%d) --tasks all \
  --replay-mode vqa --client codex --reasoning-effort medium --workers 3 --stage all \
  --judge-model gpt-6-astra --judge-effort medium > $R/vla-vqa-threejs-codex.log 2>&1 &
```

先用 `--tasks A05,I13 --dry-run` 看 `cases/<ID>/run/launch.json` 和 `prompt.txt`（应显示 `gpt-6-astra medium`，tools =
read_example/observe/report），再用 `--tasks A05,I13`（不带 dry-run，另起一个 batch 目录）跑真实冒烟，确认
`cases/A05/run/episode/mcp-calls.jsonl` 里正好是 read_example、observe（120 张图）、report 三行，然后再全量。

进度：`<batch>/progress.json`；结束标记 `<batch>/agents.finished`；结果 `results.json` / `results.md`（judge 分数在里面）。

## 5. 失败处理

- `status = failed` 且 `error` 为空：看 `cases/<ID>/run/native-stderr.log` 和 `native-events.jsonl` 最后一行的 result 事件。
  供应商侧失败（限流、内容过滤、超时）允许重试一次：把该 case 目录改名（例如 `<ID>.attempt-1`）、从 `progress.json` 的 tasks
  里删掉该条，然后同一命令加 `--resume`（只补没有 case 目录的任务）。模型正常完成但没找到 bug 不算失败，不要重跑。
- 同一个 batch 目录**只能有一个 runner** 在跑，否则 case 目录会互相冲突（`File exists`）。
- judge 阶段失败（`judge_error`）：修好 codex 登录后 `--stage judge` 重跑，已有 `judge.json` 的 case 会跳过。
- three.js 的 rubric 是 `eval/judge_sem.py` 里的 GT 句子占位（`reports/threejs-vla-profiles-20260920.json` 中标注了 placeholder）；
  如果拿到 review 站点的正式 rubric，替换 profile 里的 `rubrics_i18n.en` 后用 `--stage judge` 重打分即可。
- 磁盘：每个 episode 归档 120 帧约 3 MB，三组约 0.7 GB；judge 只用 ledger 引用的证据帧。

## 6. 导出（和 AWS 上其他模型同格式）

```bash
python3.12 scripts/native-agents/export_vla_results.py --batch $R/vla-vqa-ue-codex-<date> --out ~/vla-results --name gpt-6-astra-medium-vqa
python3.12 scripts/native-agents/export_vla_results.py --batch $R/vla-vqa-urban-codex-<date> --profiles reports/ue-urban-ipc-profiles-20260920.json --out ~/vla-results --name gpt-6-astra-medium-vqa-urban
python3.12 scripts/native-agents/export_vla_results.py --batch $R/vla-vqa-threejs-codex-<date> --profiles reports/threejs-vla-profiles-20260920.json --out ~/vla-results --name gpt-6-astra-medium-vqa-threejs
```

每个 case 输出 `judge-input.json`（最终 ledger + summary + 证据帧列表）、`rubric.json`、`frames/`、`meta.json`、`mcp-calls.jsonl`、
`prompt.txt`、`cost.json`（Codex 的 token 用量和时长）；顶层 `costs.csv`（含 `wall_s` 墙钟和 `cli_duration_s`）、`results.md`。
judge 阶段已经跑过的话，导出脚本会自动复制 judge.json、judge-metrics.json、judge 原始事件和 provenance。
GPT-6 专用计量增强还会输出 metrics.csv/json，分别记录 agent 与 judge 的 token 和墙钟耗时；订阅费用为未计价。

## 7. 参考数字（其他模型，Gemini 文本 judge 估分，不是 GPT-6 分数）

| 审计模型 | Unreal 111 | Urban 15 | three.js 87 | 费用/episode | 墙钟/episode |
|---|---:|---:|---:|---:|---:|
| gemini-3.8-flash medium | 10 | 0 | 35 | $0.24 | 76–90 s |
| claude-opus-5 medium | 7 | 1 | 35 | $0.64–0.86 | 91–132 s |

Codex 预期每个 episode 也是 3 次工具调用；输入约 6 万 token（120 张 480x288 图 + ICL + 轨迹文本）。
