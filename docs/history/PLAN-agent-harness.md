# 新 agent harness(`agent/`)设计与实施计划

## Context

现有 `harness/` 是一个每步重建 context 的单动作 ReAct 环路:最近 2-3 步带图、更早压成一行文字、丢弃模型回复,前缀每步都变(KV cache 命中率极低),没有长期记忆(模型无法回看旧帧做对比),flag 追加式不可改(`env/core.js:662`),且只服务 three.js 页面。实验记录(EXPERIMENTS.md)把跨步记忆缺失、模型不主动做对比验证列为主要瓶颈。

目标:在 `game-auditing` 里新建 `agent/` 包(旧 `harness/` 冻结不动,已发表结果可复现),做一个**环境无关、回合制、tool calling、append-only + 64k 一次性压缩、帧全部落盘可回看、带 bug 台账**的 harness。所有消融都是开关。目标模型是 vLLM 上的开源 VLM(Qwen3-VL 系列等);闭源模型走 Claude Code / Codex 自己的 harness,不在本计划范围。

已确认的决策(与用户讨论所得):
- 协议:原生 OpenAI tool calling;扁平 tool loop,没有"步"的概念,只有环境动作计数 `a<n>` 用于帧索引和预算。
- 一次模型输出里的多个环境动作按顺序执行,各自返回观察。
- 预算:环境动作数为主(默认 90),模型调用数为安全上限(默认 300)。
- flag:带 id、可改可撤、`suspect|confirmed|retracted`,证据帧引用可选;评分只用最终未撤回集合,历史全部落盘。
- 压缩后 context = system + 任务 + 模型重写后的 notes(即续接状态,不再另有一份续接笔记)+ 机械 action 索引 + bug 台账 + 最近 K 个环境动作的原始消息(默认 K=3)。
- 观察消融:`final`(动作后一张全分辨率帧)vs `film`(动作中按 sim 时间等间隔的低清帧 + 最终帧)。
- VISTA 的"行动前写预期、行动后写差异"只是 system prompt 里两句策略提示,开关,默认开,不约束输出格式。
- UE 侧:先只写客户端适配器,按"假定的" tick 模式接口;`simworld_server` 的改动另立计划。

## 研究备忘要点(vLLM 0.11.x + Qwen3-VL-Instruct,已核实)

- 服务端:`--enable-auto-tool-choice --tool-call-parser hermes --enable-prompt-tokens-details --limit-mm-per-prompt '{"image":512}' --max-model-len 98304 --mm-processor-cache-gb 16`,非流式,`tool_choice="auto"`。hermes 会解析多个 `<tool_call>`;`parallel_tool_calls` 参数被忽略。`tool_choice="required"` 走结构化输出、`content` 为空,只作无 tool call 时的一次重试。
- 前缀缓存默认开,图片按解码像素 blake3 哈希:同一帧的 base64 **必须逐字节复用**,不能重编码。`usage.prompt_tokens_details.cached_tokens` 需要 `--enable-prompt-tokens-details`,缺省视为 0。
- 图片放 `tool` 消息里 Qwen 模板可渲染,但不是跨模型通用做法;统一用 **tool 消息给文字,紧跟一条 user 消息带图**。
- 图片 token = (w/32)·(h/32)+2,尺寸先取 32 的倍数:960×576 = 540,480×288 = 135。film 一步约 1.6k 图片 token,64k 约在第 35 个动作附近触发压缩。
- `/tokenize` 不展开图片占位,token 预测用递推:`next = prev.prompt_tokens + prev.completion_tokens + est(新增消息)`,文本按 len/4,图片按公式;每次调用后对照真实 `prompt_tokens` 记录漂移。
- `env/agent.html` 已支持 `obs=film&filmDt&filmMax&filmW&filmH`;传 `filmW=960&filmH=600` 即得全分辨率胶片帧,无需改环境(`core.js:544-551`);缩略图在 harness 侧生成。

## 包结构

```
agent/
  __init__.py
  types.py        Frame / Pose / Observation / Action / ObsConfig / RunConfig(dataclass)
  env/base.py     Env 协议 + blocked 判定
  env/threejs.py  ThreeJSEnv:复用 harness/bridge.py 的 Bridge(只读引用,不改旧包)
  env/ue.py       UEEnv:HTTP 客户端,按假定的 tick 接口写
  env/fake.py     FakeEnv:PIL 画合成帧,单测用
  archive.py      FrameArchive:全分辨率落盘、index.jsonl、按 ref 取帧/裁剪、缩略图缓存
  ledger.py       BugLedger:flag/update/retract、事件日志、导出评分兼容的 flags
  notes.py        Notes:模型可写的 scratchpad(notes.md)
  llm.py          OpenAI 兼容客户端(tools、usage、cached_tokens、重试);FakeLLM 放 tests
  context.py      Conversation:append-only 消息日志、token 递推、压缩(续接笔记 + 重建)
  tools.py        tool JSON schema + Dispatcher(按能力过滤、按顺序执行、错误结果)
  prompts.py      SYSTEM(逐字节恒定)、任务模板、压缩提示、观察文本模板
  loop.py         run_episode:扁平 tool loop
  runner.py       CLI:单 episode / grid / resume;run 目录布局;meta.json 兼容
  tests/          pytest(fake env + fake llm;Chromium 集成测试打 marker)
scripts/serve_model_tools.sh   带 tool calling 与缓存参数的 vLLM 启动脚本
```

## 核心接口

### types.py

```python
@dataclass class Frame:   ref: str; kind: 'film'|'final'; t_sim: float; jpeg: bytes; w: int; h: int; path: Path|None
@dataclass class Pose:    x: float; y: float; z: float; yaw: float; pitch: float; raw: dict   # 米、度;raw = 环境原生(轨迹兼容用)
@dataclass class Observation: action_index: int; frames: list[Frame]; pose: Pose; moved: float; sim_elapsed: float;
                              events: dict  # teleported/respawned/interacted/env_note
@dataclass class Action:  kind: 'move'|'turn'|'look'|'interact'|'wait'; params: dict   # 米/度/秒
@dataclass class ObsConfig: mode: 'final'|'film'; film_dt: float=0.5; film_max: int=8;
                              capture_w=960; capture_h=600; ctx_final=(960,576); ctx_film=(480,288); jpeg_q=85
```

### env/base.py

```python
class Env(Protocol):
    name: str
    capabilities: frozenset[str]            # ⊆ {move, turn, look, interact, wait}
    def reset(self, config: str, seed: int, obs: ObsConfig) -> Observation   # a0,只有 final 帧
    def step(self, action: Action) -> Observation                            # 调用之间世界冻结
    def meta(self) -> dict                                                   # renderer、load_time 等
    def close(self) -> None

def blocked(action, obs) -> bool:   # 环境无关:move 且 (cmd - moved) > max(0.25, 0.1*cmd) 且未传送(沿用 harness/runner.py 的 audit 规则)
```

- `ThreeJSEnv`:`Bridge.open_env(config, seed, extra={obs, filmDt, filmMax, filmW, filmH})`;`act` 映射 move→forward/back(dist)、turn(deg)、look(deg)、interact、wait(ms)。坐标 (x, y_up, z) → Pose(x=x, y=z, z=y_up),yaw/pitch 原样。`res.film` 与 `res.frames[-1]` 解 base64 成 Frame。能力全集。
- `UEEnv`(假定接口,服务端另做):`POST /envs/{e}/agents/{a}/step`,请求增加 `"clock": "tick"` 与 `"film": {"dt", "max_frames"}`,响应增加 `"frames": [{"t", "rgb"}]`。move(m) → choice 1,duration = m / (speed cm/s ÷ 100);turn → choice 2 + clockwise;wait → choice 0。厘米→米,UE 的 x/y 水平、z 向上直接对应 Pose。能力 {move, turn, wait}。用 FakeHTTP 单测;在计划文档里把这个契约写进 `env/ue.py` 的 docstring,作为 simworld_server 改造的规格。
- `FakeEnv`:确定性;位置文字与色块画进帧;可配置某方向 blocked、某动作后 teleported,用于测 blocked 提示与事件文本。

### archive.py

- 目录 `runs/<tag>/<ep>/frames/`,文件 `a012.jpg`(final)、`a012_f03.jpg`(film),`index.jsonl` 每行 {ref, file, kind, t_sim, action, w, h, pose}。
- ref 语法:`a12` = 第 12 个动作的最终帧,`a12.f3` = 其第 3 张胶片帧,`a0` = 初始观察。
- `put(obs)`、`get(ref, region=None, max_side=960) -> bytes`(裁剪区域用 0-1 归一化坐标,输出边长取 32 的倍数)、`ctx_image(ref, size)` 生成并**缓存** data URL(同一 ref 同一尺寸只编码一次,保证前缀缓存命中)。

### ledger.py

- `flag(description, category, status, evidence, pose, action_index) -> id`(`b1, b2...`);`update(id, **fields)`;状态机 suspect ↔ confirmed → retracted;每次变更写 `bugs.jsonl`。
- `render()`:压缩重建与 `list_bugs` 用的文本表。
- `export()`:评分兼容,`[{pos: raw 三维, note: description, simT, id, status, category, evidence, action}]`,只含未撤回项;`export_history()` 全量。

### llm.py

- `chat(messages, tools, tool_choice='auto', max_tokens) -> {message(原样 dict, 含 content 与 tool_calls), usage{prompt, completion, cached}, latency}`;沿用 `harness/vlm.py` 的重试策略;非流式。
- 无 tool call 时由 loop 决定重试(先追加 nudge,再一次 `tool_choice='required'`)。

### context.py

- `Conversation`:`messages` 列表只追加;`append_assistant(msg)` 原样存;`append_tool(call_id, text)`;`append_user_images(label, [(caption, data_url)])`;`snapshot()` 深拷贝供 loop 发请求。
- token 记账:`record_usage(usage)` 后 `predicted_next()` 按递推公式;每次收到真实 `prompt_tokens` 记录 `drift` 到 `calls.jsonl`。
- `needs_compaction()`:`predicted_next() > context_limit`(默认 64000)。
- `compact(llm, note_request, rebuild_ctx)`:
  1. 追加 user 消息 `COMPACT_PROMPT`(写续接笔记,固定栏目:任务进度 / 已检查与未检查区域(引用 `a<n>`)/ 可疑点与证据帧 / 台账判断 / 下一步计划;≤ 300 词),`tools=None` 调用一次,存 `context/note_<n>.md`。
  2. 把旧消息列表整体写 `context/epoch_<n>.json`(图片以 ref 代替 base URL)。
  3. 重建:`[system(逐字节相同)] [user: TASK + "[Continuation #n, actions a0..a37 / 90]" + 笔记 + action 索引 + 台账 + notes.md + "Recent actions follow verbatim."]`,然后**原样**复制从"发出第 N-K+1 个环境动作的那条 assistant 消息"起的全部消息(tool_call_id 自然匹配)。
- action 索引由 loop 维护:每个环境动作一行 `a12 move forward 2.0 -> moved 1.98 pos(1.20,-0.30) yaw 90 | frames a12.f0-f3, a12`,含 BLOCKED / teleported 标记。

### tools.py

tool 列表(按 `env.capabilities` 与 `--tools` 开关过滤):

| tool | 参数 | 返回 |
|---|---|---|
| move | distance_m (0.3-4), direction forward/back | 观察文本 + 图片消息 |
| turn | degrees (-180..180, + 右) | 同上 |
| look | degrees (+ 下) | 同上 |
| interact | 无 | 同上 |
| wait | seconds (0.5-5) | 同上 |
| done | summary | 结束 |
| inspect | refs (1-4), region? [x0,y0,x1,y1] | 归档帧原分辨率或裁剪,作为图片消息重新注入 |
| history | from_action, to_action (≤ 40) | 该区间模型自己的文字、工具调用与结果(来自 actions.jsonl) |
| flag_bug | description, category ∈ {geometry, collision, visual, state, semantic, other}, status suspect/confirmed, evidence? refs | id + 当前台账摘要 |
| update_bug | id, description?, status? (含 retracted), evidence? | 同上 |
| list_bugs | 无 | 台账 |
| write_notes | text | 追加一条到 notes.md(epoch 内增量记);压缩时模型整份重写 notes 作为续接状态,read_notes 已删(内容总在 context 里) |

- `Dispatcher.run(tool_calls) -> list[ToolResult(text, images)]`:按顺序执行;未知工具或参数越界返回错误文本不抛异常;每个环境动作立刻产生观察并追加(tool 文本 + user 图片消息);`inspect` 每次 ≤ 4 帧。
- 观察文本模板(proprio 开):`a12 move forward 2.0m -> moved 1.98m | pos (x=1.20, y=-0.30) yaw 90 pitch 0 | sim +0.40s | frames: a12.f0..a12.f3 (film), a12 (final)`,blocked 且 hint 开时追加 `[BLOCKED - something invisible or solid is in the way]`;proprio 关时只给 `executed` 与帧引用。图片消息:`[observation a12] t=+0.0s <img> ... final <img>`,film 帧用 ctx_film 尺寸,final 用 ctx_final。

### prompts.py

- `SYSTEM` 逐字节恒定,不含任务与配置:QA 角色、五类 bug 分类学(沿用 `harness/policies/vlm_policy.py` 的 AUDIT_SYSTEM 文案)、工具用法与 ref 语法、台账语义(先 suspect 再验证,可撤回)、观察格式说明(final / film 两段,按模式选一段)、预算说明、以及可选的两句预期对照策略(`--expect`)。SYSTEM 的变体由开关决定但在一次运行内固定。
- 任务指令沿用 `harness/tasks.py` 的 `TASKS[name]["instr"]`,放第一条 user 消息。

### loop.py

```
obs0 = env.reset(); archive.put; conv = [system, user(task + observation a0 文本), user(图片)]
while True:
    if conv.needs_compaction(): conv.compact(...)
    resp = llm.chat(conv.snapshot(), tools); conv.append_assistant(resp.message); log call
    if no tool_calls: nudge 一次 → 再无则 tool_choice='required' 一次 → 再无则结束(outcome=no_action)
    results = dispatcher.run(tool_calls)      # 环境动作即时执行并追加观察
    if done called: break
    if n_actions >= max_actions or n_calls >= max_calls: 追加预算耗尽提示后 break
```

## 运行目录与评分兼容

`runs/<tag>/<task>-s<seed>/`:
- `frames/` + `frames/index.jsonl`(归档);`frames.jsonl`(`eval/video.make_video` 用,file 为 `frames/...` 相对路径,caption 与旧格式一致)
- `actions.jsonl`(每个环境动作:index、action、moved、pose、blocked、events、发起它的调用号、模型该次 content)
- `calls.jsonl`(每次模型调用:usage、cached_tokens、latency、tool 名列表、预测 vs 真实 prompt_tokens)
- `bugs.jsonl`、`notes.md`、`context/epoch_<n>.json`、`context/note_<n>.md`、`transcript.jsonl`(全部消息,图片用 ref)
- `trajectory.jsonl`:兼容 `eval/metrics.py` / `eval/plot_traj.py` 的旧字段(step=action index,action 映射回 `forward/back/turn/look/interact/wait/flag` 形状,pos 用 `pose.raw`,yaw/moved/blocked/teleported/respawned)
- `meta.json`:旧字段(task、config、model、seed、kind="audit"、proprio、obs、film_dt、film_max、steps_budget、steps_used、started/ended、renderer、flags=ledger.export()、vlm_usage、page_errors)+ 新字段(context_limit、compactions、calls、cached_ratio、tool_counts、bugs_history、outcome)。
- 任务名与目录名沿用 `audit_<case>_<variant>-s<seed>`,`eval/judge_sem.py` 与各 report 脚本无需改动即可评分。

## CLI 与消融开关(runner.py)

`python -m agent.runner --task audit_sp05_bug --env threejs --model ... --base-url ...`,grid 模式 `--grid a,b --episodes 3 --parallel 4 --tag ... --resume`(沿用 `harness/runner.py` 的 spawn Pool 与 resume 逻辑)。

| 开关 | 默认 | 含义 |
|---|---|---|
| `--env threejs\|ue` | threejs | 适配器 |
| `--obs final\|film` | film | 观察模式 |
| `--film-dt / --film-max` | 0.5 / 8 | 胶片采样 |
| `--ctx-final / --ctx-film` | 960x576 / 480x288 | 进 context 的尺寸 |
| `--context-limit` | 64000 | 压缩阈值 |
| `--keep-recent` | 3 | 压缩后保留的环境动作数 |
| `--tools` | memory,bugs,notes | 关掉 memory 即无 inspect/history(退化为纯 append-only 消融) |
| `--expect on\|off` | on | 预期对照提示 |
| `--proprio / --blocked-hint` | 1 / 0 | 与旧 harness 同义 |
| `--max-actions / --max-calls` | 90 / 300 | 预算 |
| `--temperature / --max-tokens` | 0.4 / 600 | |

## 实施顺序

1. `types.py`、`env/base.py`、`env/fake.py`、`archive.py`、`ledger.py`、`notes.py` + 单测。
2. `llm.py`(含 usage 细节)+ `tests/fake_llm.py`(脚本化 tool call 序列)。
3. `context.py`:append-only、递推记账、压缩重建 + 单测(前缀不变性、K 尾巴、索引与台账进入重建消息)。
4. `prompts.py`、`tools.py`、`loop.py` + FakeEnv/FakeLLM 端到端单测(多环境动作顺序、inspect 注入、flag 生命周期、预算终止、无 tool call 重试)。
5. `env/threejs.py` + Chromium 集成测试(env0-corridor,final 与 film 两种模式各跑一段脚本化动作,校验帧数、t_sim 间隔、归档文件)。
6. `runner.py`:目录布局、meta/trajectory/frames 兼容输出、grid/resume;`scripts/serve_model_tools.sh`。
7. `env/ue.py` + FakeHTTP 单测,docstring 写明假定契约。
8. 服务器上真机冒烟(Qwen3-VL-8B,`audit_sp05_bug` 与 `audit_sp00_clean` 各 1 个 episode,film 与 final 各一次),跑 `eval/judge_sem.py` 与 `eval/video.py` 确认兼容。

## 验证

- 单测:`.venv/bin/pytest agent/tests -m "not chromium"`;集成:`-m chromium`(本机与服务器都可跑)。
- 前缀稳定性:单测断言同一 epoch 内第 n 次请求的消息序列化是第 n+1 次的严格前缀;真机上 `calls.jsonl` 的 `cached_tokens/prompt_tokens` 在 epoch 内应稳定上升到 80% 以上,压缩后一次回落再恢复。
- token 记账:`calls.jsonl` 中预测与真实 `prompt_tokens` 的漂移应 < 3%;压缩在 64k ± 一次观察内触发。
- 观察消融:同一动作序列下 `final` 每动作 1 帧、`film` 每动作 ≤ 9 帧,`t_sim` 间隔 = film_dt。
- 记忆:脚本化模型在 a30 调 `inspect(["a5"])` 时收到的图片字节与归档 `a005.jpg` 一致;压缩后 `history(1,10)` 能返回被丢弃步骤的文字。
- 台账:flag → update(confirmed) → update(retracted) 后 `meta.json.flags` 为空、`bugs.jsonl` 三条事件。
- 评分兼容:真机 episode 上 `python -m eval.judge_sem runs/<tag>` 正常出矩阵,`python -m eval.video runs/<tag>/<ep>` 出视频。

## 不做的事

- 不改 `harness/`、不改 `env/core.js`(胶片全分辨率靠已有 URL 参数)。
- 不改 `simworld_server`(契约写在 `env/ue.py` docstring,另立计划)。
- 不做 explorer/auditor 拆分、不做 read_pixels、不做跨 episode 的持久记忆。


## 修订(2026-09-08,实现后)

- notes 与续接笔记合并:`write_notes` 是 **append** 语义(epoch 内随手记一条,便宜);压缩时的提示把当前 notes 原文引给模型,要求 **整份重写** 为续接状态,回复覆盖 notes.md,header 里附的就是它。`read_notes` 删除:epoch 内 append 的内容留在 tool call 参数里,压缩后在 header 里,模型总能看到。
