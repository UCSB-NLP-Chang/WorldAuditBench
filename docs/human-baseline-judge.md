# Human baseline 专用二元 judge

入口 `judge.judge_human_baseline` 使用 `judge/judge_human_baseline_prompt.md`。
原始 `judge/judge.py` 和 `judge/judge_prompt.md` 保持不变。入口在独立模块实例中加载原 judge，仅选择专用 prompt，复用相同 CLI 参数、模型调用、图片处理、二元 JSON schema 和用量记录。

```sh
cd /home/ec2-user/game-auditing
.venv/bin/python -m judge.judge_human_baseline \
  --rubrics /path/to/rubric.json \
  --model-output /path/to/judge-input.json \
  --images /path/to/evidence.png \
  --model gpt-6-astra --reasoning-effort medium \
  --output /path/to/human-judge.json
```

评分单位是一份人类提交，至少一条报告命中目标核心异常即为1。允许报告与其引用截图联合定位异常；不因省略辅助复现步骤、精确阈值、后续重生、正常碰撞属性等单独扣分。不同核心异常、错误对象、无法确定所指异常的空泛报告及明确反证仍为0。

本入口是独立 human baseline 评分口径。与使用原始 prompt 的模型评分比较时，需要明确说明口径差异。原始评估结果和新结果均保留。

测试：

```sh
.venv/bin/python -m pytest -q tests/test_binary_judge.py tests/test_human_baseline_judge.py
```
