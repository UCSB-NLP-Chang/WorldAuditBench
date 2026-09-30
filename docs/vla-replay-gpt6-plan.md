# GPT-6 Astra medium VLA replay 实验执行计划

## 目标与授权范围

用户已同意使用当前 ChatGPT 账号的 Codex 订阅额度，但只为本次实验登录和使用。
范围：已有 VLA recording 的 Unreal 111、Urban 15、Three.js 87，共 213 个任务；
审计模型与二元 judge 均固定为 `gpt-6-astra`、reasoning `medium`。
包括必要的 A05/I13 冒烟、故障诊断及交接文档允许的失败重试。
不包含其他模型结果的重新评分、其他项目、通用编码或常驻服务。不得把此登录设为服务器默认登录。

## 已核实与待验证

- 仓库：awsunreal 的 /home/ec2-user/game-auditing；检查时分支 iclr，HEAD 3ef1eb0。
- ec2-user 默认 `codex login status` 返回 Not logged in；未设置 CODEX_HOME，默认 auth.json 不存在。
- CLI 支持 `login --device-auth`。现有 /home/ec2-user/.local/bin/codex 只设置 Node PATH，不选择其他账号。
- scripts/native-agents/launch.py 的 Codex 分支及 eval/judge.py 都使用子进程环境，强制 ChatGPT 登录并去掉 OPENAI_API_KEY / CODEX_API_KEY。
- OpenAI 官方文档支持把 file 登录存储放在 CODEX_HOME/auth.json，以及远程设备码登录：
  https://learn.chatgpt.com/docs/auth
- 因而专用登录方案可行；尚未完成账号登录、额度/目标模型访问验证、真实 agent + judge 冒烟。
  不把“机制可行”记作“实验已经跑通”。

## 实验专用登录

专用目录：/home/ec2-user/.local/state/vla-gpt6-astra-medium/codex-home
目录权限 700，凭据文件权限 600，位于仓库和结果归档之外。
用全新浏览器/设备码授权登录用户指定的同一个 ChatGPT 账号，不复制当前应用的认证文件。

仅在本实验命令及其子进程中设置 CODEX_HOME；不写入 shell profile、全局环境或系统服务。
采用一个专用 wrapper，并仅对本实验 runner 的 PATH 加入该 wrapper 目录。
wrapper 固定专用 CODEX_HOME 和 file 凭据存储，转发到服务器现有 Codex CLI。
这样 agent 的 launch.py 与 judge 中的 shutil.which("codex") 均选择同一 wrapper；
即使调用带 --ignore-user-config，凭据存储仍由显式 CLI 参数指定。

建议 wrapper 路径：/home/ec2-user/.local/state/vla-gpt6-astra-medium/bin/codex

```sh
#!/bin/sh
exec env -u OPENAI_API_KEY -u CODEX_API_KEY -u CODEX_ACCESS_TOKEN \
  CODEX_HOME=/home/ec2-user/.local/state/vla-gpt6-astra-medium/codex-home \
  /home/ec2-user/.local/bin/codex \
  -c 'cli_auth_credentials_store="file"' "$@"
```

准备目录/wrapper 后，只通过此 wrapper 运行：
```sh
/home/ec2-user/.local/state/vla-gpt6-astra-medium/bin/codex login --device-auth
/home/ec2-user/.local/state/vla-gpt6-astra-medium/bin/codex login status
```

由用户在浏览器中完成账号授权，不索取密码，不把 token、auth.json 或设备码写入实验文档/结果。
若设备码方式不可用，用 SSH 转发 localhost:1455 的浏览器登录，仍使用同一 wrapper。
登录后核对账号为用户指定账号；记录非敏感的验证结论。
普通 /home/ec2-user/.local/bin/codex login status 应继续是未登录。

边界：CODEX_HOME 是本地登录与配置隔离，不是 OAuth 的实验级权限或独立额度。
同一 Linux 用户的其他进程、管理员仍可能读取该目录；不向其他任务提供目录或 wrapper。
本实验与用户其他 Codex 使用共享账号额度，不能保证 213 题无需额度等待。

## 执行与验证

1. 按 vla-replay-handoff.md 检查 Python 环境、录像、ICL 和 profile；运行已有协议测试。
2. 先核对旧批次的实际帧尺寸。当前文档写 480x288，代码默认按图像字节预算自适应；
   正式运行前确定与对照组一致的配置并记录，不暗改实验条件。
3. 所有 runner 使用以下进程级前缀，以保证 agent 与 judge 的 Codex 都是专用 wrapper：
   `env PATH="/home/ec2-user/.local/state/vla-gpt6-astra-medium/bin:$PATH"`
   不另外传 --cli 指向默认 Codex。若单独调用 eval.judge，同样使用此前缀。
4. A05/I13 dry-run 使用独立 batch；显式设置：
   `--client codex --model gpt-6-astra --reasoning-effort medium --replay-mode vqa --judge-model gpt-6-astra --judge-effort medium`。
5. 真实冒烟使用另一个 batch 和 --stage all，先 --workers 1 --judge-workers 1。
   核对 launch.json、实际 Codex 命令/事件、read_example → observe → report 三次调用、
   录像帧完整性，以及两题的 judge.json、judge-provenance.json。
   确认 agent 与 judge 均为 gpt-6-astra medium，且都通过实验专用登录。
6. 冒烟通过后执行交接文档的三个完整批次，共 213 题。
   初始按文档每批 --workers 3，依据实际限流调整；每个 batch 只能有一个 runner。
   使用上述 PATH 前缀和显式模型参数，--stage all 自动完成审计和 judge。
7. judge 链路：
   run_vla_replay.py → .venv/bin/python -m eval.judge → 专用 wrapper → codex exec。
   每题独立上下文，输入 rubric、最终 ledger/summary 及引用证据截图，输出二元 score 和 reason。
   rubric 不提供给被测审计模型；judge 不读取审计推理过程。
8. 模型正常完成但未找到 bug 不重跑；供应商失败按交接文档最多补试一次。
   若遇额度限制，保留进度并等待额度恢复，不切换账号、API key、模型或推理强度。
   单独 --stage judge 也必须使用同一专用 PATH 前缀。
   Three.js 当前 rubric 为占位 GT 句子，结果明确标记；补正式 rubric 后的重评分仍限本次 GPT-6 输出。
   注意 runner 会跳过已有 judge.json，重评分需先归档旧评分，保留版本与依据。

## 结果与完成条件

导出至 ~/vla-results/：
- gpt-6-astra-medium-vqa
- gpt-6-astra-medium-vqa-urban
- gpt-6-astra-medium-vqa-threejs

包含报告、证据帧、评分输入、rubric、MCP 记录、模型参数、token 用量和耗时。
导出脚本现已自动复制 judge.json、judge-metrics.json、评分 provenance 及原始事件。
按三个数据集分别核验完成数、评分数、命中数和失败数；失败不可默认为未命中。
订阅用量/耗时与估算 API 价格分开，不把估算标作实际账单。

## 实验结束后的登录清理

所有本实验 agent/judge 进程退出、结果导出并核验后：
1. 用专用 wrapper 执行 codex logout。
2. 验证专用 wrapper login status 返回 Not logged in，专用 auth.json 已移除。
3. 删除仅本实验的 wrapper 和残留认证缓存；保留非敏感实验结果。
4. 确认默认 Codex 登录未被改变，不操作用户本机或其他登录环境。

## Smoke test 记录

正式实验前 A05/I13 smoke test 已通过审计 + judge 全链路验证；尚未启动 213 题全量。
- 专用 ChatGPT 登录有效，默认 Codex 仍未登录。登录只保留供本实验后续运行；结束后执行上述退出与清理。
- 26 项协议测试通过。两题各 read_example → observe → report 共 3 次调用；observe 各交付完整 120 张图，无错误。
- A05：68.4 s，报告 1 条 bug，GPT-6 medium judge 得分 1。
- I13：60.4 s，报告 0 条 bug，GPT-6 medium judge 得分 0；正常未命中，不重跑。
- Dry-run：out/native-agents/batches/vla-vqa-gpt6-medium-smoke-dry-20260921
- Smoke：out/native-agents/batches/vla-vqa-gpt6-medium-smoke-20260921
- 验证：该 smoke 目录的 smoke-verification.json；逐题 smoke-cost.json 保存 Codex token 用量。
- 报告：reports/vla-gpt6-smoke-20260921.md
- 帧配置已核对旧 Gemini/Opus 批次，保持 inline_full_res=true（自适应尺寸）。
- 全量结果导出前需补齐 Codex turn.completed 用量解析；现有 export_vla_results.py 只解析 result 事件，会漏 token。
  当前 eval/judge.py 也未持久化 judge CLI 的用量，不能将 agent 用量冒充 agent+judge 总用量。
- vqa 的 frames_coverage=0 来自 play 计数，不能解读为没看录像；使用实际 observe 图像数验证覆盖。

## 全量执行状态（2026-09-21 UTC）

用户已授权启动全量，三个 batch 已并发启动，审计/评分均固定 gpt-6-astra medium。
每组审计 workers=3、judge-workers=2；不录制新录像、不使用 GPU。
全部 213 题输入预检通过；45 项测试通过；真实 judge 指标验证通过。

指标修复：
- eval/codex_metrics.py 解析 Codex turn.completed，正确记录输入、缓存、输出、推理及总 token；未知值为 null。
- launch.py 记录 CLI 子进程墙钟耗时。
- eval/judge.py 保存 judge-native-events.jsonl、judge-native-stderr.log、judge-metrics.json。
- export_vla_results.py 自动复制 judge 结果并导出 metrics.csv/json、costs.csv；
  包含逐题模型/effort、两阶段用量和耗时、分数/理由、证据数、120 帧交付计数、工具调用和错误。
  订阅费用不计作 $0，保留未计价/null。
- 修复仅增加计量/导出，未改变 prompt、rubric、图像设置或评分逻辑。
- 启动时另一个会话对 runner 的 Qwen 默认名称有修改；已保留，该实验显式指定 GPT-6 不受影响。
- 真实计量验证结果：out/native-agents/metrics-validation/judge-check。

数据盘根目录：/mnt/auditor-build/vla-gpt6-medium-20260921
- batches/{ue,urban,threejs}：原始完整运行产物。
- exports/gpt-6-astra-medium-vqa{,-urban,-threejs}：分组导出，完成后链接至 ~/vla-results 同名目录。
- status.json、{ue,urban,threejs}.log：运行状态与进度。
- preflight.json、provenance.json、source-snapshot/：任务清单、命令、代码指纹和源码快照。
- summary.json、all-metrics.json：全部批次结束后生成。
- 每组导出的 verification.json 自动检查每一题完整性。失败/缺失保持可见，不记成未命中。
独立后台 supervisor 已启动，断开 SSH 不会终止任务。当前尚未完成全量结果核验。

## 运行中协议检查

Urban 已完成 15 题审计与评分，指标完整，但 U018/U028 额外 observe 一次，严格三调用校验未通过。重复读取内容和图像引用已单独核对；保留原始结果，不重跑、不在批次中途改变协议。详见 Urban 导出的 protocol-review.json 和 verification.json。

## 全量后台完成记录

状态：needs_attention。报告：reports/vla-gpt6-full-20260921.md；总表：/mnt/auditor-build/vla-gpt6-medium-20260921/all-metrics.csv。

## 全量后台完成记录

状态：complete。报告：reports/vla-gpt6-full-20260921.md；总表：/mnt/auditor-build/vla-gpt6-medium-20260921/all-metrics.csv。

## 最终统计口径

按用户澄清仅看 judge 分数，全部 213 题纳入，不以工具调用次数过滤或改分。重复同一 observe 作为描述性指标保存；原三调用检查存于 verification-strict-three-calls.json，导出完整性核验已通过。最终 UE 6/111、Urban 1/15、Three.js 28/87，合计 35/213。未重跑或修改任何 judge 分数。已运行最终导出报告与实验专用登录清理。
