# GPT-6 二元 Judge CLI

输入 **rubric + 模型输出 + 可选截图**，输出只有 `reason` 和 `score`（整数 0/1）。每次调用评分一个任务。默认使用项目已有的 Codex 登录方式及 `gpt-6-astra`，推理设置为 `medium`；不启动游戏，也不替换指定模型。可按 task ID 从统一 Hugging Face 数据集中读取 rubric；评分指令使用仓库中的 `eval/judge_prompt.md`。当前公开 rubric 只有 `anomaly` 和 `expected`，历史实验保留原始评分输入。

## 使用

使用统一任务数据评分，无需另存 rubric 文件：

```bash
python3 -m eval.judge --task S01 --model-output agent_output.json
```

首次自动下载固定版本的数据表，之后复用缓存。`--dataset` 可指定本地 Parquet。下面的 `--rubrics` 入口保留给自定义数据和历史实验。

先安装 Codex CLI 并完成 `codex login`。带图时还需要 `python3 -m pip install pillow`。

在仓库根目录运行，不传图：

```bash
python3 -m eval.judge \
  --rubrics rubric.txt \
  --model-output agent_output.txt
```

传入多张图并保存结果：

```bash
python3 -m eval.judge \
  --rubrics rubric.json \
  --model-output agent_output.json \
  --images before.png after.png \
  --output result.json
```

两个文本文件支持 UTF-8 txt、Markdown 或 JSON，原文作为数据传入，不要求包装成固定 schema。模型输出可以是最终回答或 bug ledger；请提交最终结果，避免混入模型身份、其他 judge 结论或完整评测答案。截图支持 PNG/JPEG/WebP，顺序与命令行一致，不会只取前三张。不要给 judge 提供包含全部任务答案的 catalog。

输出示例（示意，不是该命令的实测结果）：

```json
{"reason":"模型明确指出目标沙发悬空，与 rubric 的核心异常一致。本次未提供截图，依据文本匹配判断。","score":1}
```

`--model`、`--reasoning-effort`、`--timeout`（默认 300 秒）、`--codex-bin` 可显式设置。调用使用现有 ChatGPT 登录，不回退到环境中的 API key。每次创建独立上下文，忽略个人 Codex 配置并关闭 shell、web 和多 agent 工具。

## 固定评分规则

- 至少一条最终发现正确匹配目标对象及核心异常，关键条件成立，且没有明确图像反证：**1**。
- 未发现、描述错误或过于空泛、未描述必要条件、图像明确反驳目标发现：**0**。
- 不传图仍可得 1；图片仅作辅助核对，除非 rubric 明确要求视觉证据。图片不清楚不自动等于错误，judge 必须在原因中说明局限。
- 同义表达和分类标签不同不会单独扣分。重复报告不重复得分，额外报告不抵消已经成立的目标发现。
- 静态图不能代替模型对动态变化的描述；也不能凭 rubric 猜图。存在变化类 bug 的输出必须描述变化和必要条件。

完整评判指令保存在 [`eval/judge_prompt.md`](../eval/judge_prompt.md)。只有一个二元结果，不输出三分类、置信度或附加指标。Success rate 为正常完成评分的任务中 `score` 的均值；同一比较应固定 judge 模型、prompt、参数及图片提供方式。

CLI 成功返回 JSON 时退出码为 0，**即使分数为 0 也不表示程序失败**。输入文件损坏、登录/模型调用失败、超时或无效 JSON 输出时，退出码为 2，错误写入 stderr，不伪造 score=0，也不覆盖旧结果文件。这些调用应修复后重跑并单独记录，不能混入有效评分分母。

## 与既有评测兼容

这是独立入口，不改动用于旧实验复现的 `eval.judge_sem`、缓存、任务答案或线上审核服务。核心只依赖 Python 标准库；图片解码复用项目已有 Pillow 依赖。

实现依据：[Codex 非交互与结构化输出](https://learn.chatgpt.com/docs/non-interactive-mode)、[CLI 图片参数](https://learn.chatgpt.com/docs/developer-commands?surface=cli)。实际参数同时经过本机 `codex exec --help` 核对。

离线测试（需要 pytest 和 Pillow，不调用模型）：

```bash
python3 -m pytest -q tests/test_binary_judge.py
```
