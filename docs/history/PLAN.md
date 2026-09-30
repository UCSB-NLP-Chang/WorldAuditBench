# Embodied Bug-Hunt Benchmark — 项目计划

> 本文档写给执行开发的 coding agent。reference/ 目录里是人工验证过的原型,
> 它们证明了技术路线可行,但**不是**最终架构 —— 你的工作是按本计划重构与扩展,
> 而不是在原型上继续堆代码。所有原型都在 Mac Chrome 上人工跑通过。

---

## 1. 项目背景

**核心假设**:游戏/3D 环境中存在一类 bug,只有通过具身交互(移动、开门、拉杆、
观察时序)才能发现,纯图像/视频判读(VQA)发现不了。验证这个假设,就证明了
embodied VLM agent 相对纯 VLM 的不可替代性。

**Bug 分类学**(按发现所需能力分层):
- **L1 单帧可见**:悬浮物体、贴图丢失、比例错误 —— 看一眼截图就能发现
- **L2 需要移动**:空气墙、假地面、单面消失 —— 需要走位/多视角
- **L3 需要交互+时序**:门延迟响应、门开了过不去、拉杆无效、传送门送错 ——
  必须操作并观察前后帧变化

**两条赛道**:
- **Track P(passive)**:固定轨迹的帧序列 → VLM 判读有无 bug。作 baseline。
- **Track A(interactive)**:VLM 闭环控制 agent,自主探索并 flag。
- **论文主结果 = Track A 相对 Track P 的检出增益**,预期增益集中在 L3。

**当前阶段**:在测 bug 之前,先回答一个前置问题 —— 当前 VLM 是否具备最基础的
闭环导航能力。没有导航,后面全是空中楼阁。

---

## 2. 三个已定设计决策

### 2.1 环境从简开始(环境阶梯)

不直接用完整世界。四级环境,逐级解锁:

| 级别 | 内容 | 用途 |
|---|---|---|
| **env0-corridor** | 纯程序化几何:一条 20m 走廊 + 1 扇可交互门 + 1 个发光目标环。零外部下载,秒级加载 | harness 冒烟测试、动作空间调参、CI |
| **env1-sponza-nav** | 仅 Sponza,无 bug,放 2-3 个发光目标环 | 导航能力探针(S1 实验) |
| **env2-sponza-2bugs** | Sponza + 恰好 2 个 bug:1 个空气墙(L2)+ 1 个悬浮箱(L1) | 首次 bug 检测实验(S2) |
| **env3-buggy-world** | 完整三区域(Sponza+地牢+宝库)、9 个预埋 bug、传送门、门/拉杆/宝箱交互 | 正式 benchmark(S3/S4)。reference/buggy-world.html 就是它的原型 |

环境由**配置驱动**:场景组合、bug 清单、目标点全部来自 JSON 配置文件,
代码里不硬编码。这样 env2 和 env3 只是不同的配置。

### 2.2 UI 与 agent 入口分离

原型把人类 UI(菜单、答案面板、指针锁定)和环境逻辑混在一个文件里。重构为:

```
env/core.js        场景构建、物理、交互系统、__env API —— 无任何 UI
env/human.html     引 core + 指针锁定控制 + 菜单 + 答案面板 + V键调试
env/agent.html     引 core,零 UI,加载即 agentMode,URL 参数选配置
                   例: agent.html?config=env1-sponza-nav.json
```

人类入口**必须保留**——标注 ground truth、验证新 bug、debug 全靠它。
但 agent 入口做到:
- 不加载答案数据(answers JSON 只被 eval/ 评分模块读取,永不进 agent 页面或 prompt)
- 无 beacons、无 helpers、无 V 键
- 渲染画面是纯 3D 帧(原型已保证:HUD 全是 DOM 元素,不进 canvas)

### 2.3 实验递进(gate 制,不许跳级)

| 阶段 | 内容 | 关键指标 | 进入下一阶段的 gate |
|---|---|---|---|
| **S0 冒烟** | 脚本策略(无 VLM)在 env0 执行全部动作各 20 次 | 无 JS 报错、帧非空非黑、blocked 检测正确、interact 多帧时序正确 | 全绿 |
| **S1 导航探针** | env1,三个任务:①可见目标(视觉伺服) ②背后目标(搜索) ③跨区多阶段。每任务 ≥10 episodes × ≥2 模型 × proprio on/off | SR、误报 done 率、步数、blocked 次数、原地打转事件 | 最强模型在任务① SR ≥ 60%。不达标 → 不是继续换模型,而是回来改动作空间/加导航辅助 |
| **S2 定点查验** | env2,指令"去 X 附近检查有无异常"(给方位提示,把导航难度降到最低,隔离出 bug 识别能力)。**必须含等量无 bug 对照 episodes** | 检出率、误报率(对照组 flag 即误报)、定位误差 | 空气墙检出率显著高于对照组误报率 |
| **S3 自由探索** | env3,200 步预算,自由 flag。含 clean 对照组 | precision / recall / 每个 bug 的发现步数 / L1-L3 分层检出率 | — |
| **S4 Track P 基线** | 脚本全覆盖轨迹抽帧(2-4 fps)→ 同批 VLM 判读 | 同 S3 的检出指标 | 计算 A−P 增益 = 主结果 |

S1 若不过 gate,备选导航辅助按侵入性排序:① 动作结果里加"受阻"文字提示
(proprio 已含) ② 画面叠加罗盘 ③ 恢复 goto(路点) 高层动作 —— 每加一项都要
作为消融记录,因为它改变了"我们到底在测什么"。

---

## 3. reference/ 原型说明

| 文件 | 是什么 | 重构去向 |
|---|---|---|
| `buggy-world.html` | 完整 env3 原型:三区域组装、BVH 碰撞、胶囊体移动、门/拉杆/宝箱/宝石/传送门交互、9 个预埋 bug、答案面板、**已含 `window.__env` agent API**(离散动作、interact 返回 t0/0.7s/2.8s 三帧、状态查询、flag) | 拆成 env/core.js + 两个入口 + env3 配置 |
| `vlm_nav.py` | S1 的 harness 原型:Playwright 桥接、OpenAI 兼容 VLM 客户端、3 个导航任务、滚动上下文(最近 3 帧带图,更早的转文字)、逐步日志 JSONL + 帧落盘、成功判定(距目标 <3m)、blocked 统计 | 拆成 harness/ 各模块 |
| `three_env.py` | 更早的通用 Playwright 桥,含 GPU/软渲染检测、静态服务器 | 并入 harness/bridge |
| `bug-walk2.html` | 人工 bug 注入工具:准星瞄准注入 15 类 bug、G 键登记任意 mesh 为门、V 键显示隐形碰撞、导出 JSON | 保留为独立标注工具,升级为写 env 配置格式 |

**原型中已验证的关键机制**(重构时必须保留):
- 碰撞用 three-mesh-bvh(StaticGeometryGenerator + MeshBVH + capsule shapecast),
  重建 1-2 秒,支持动态排除 mesh(穿模 bug 的实现基础)。不要退回 Octree(重建 10s+)。
- 门/闸的碰撞是"冻结的闭合 AABB + activeFn 开关",不跟随动画 —— 这正是
  "幽灵门/穿门"两类 bug 的实现机制,是特性不是缺陷。
- 移动是位置驱动,速度向量**只承载竖直分量**(见 §6 坑 #9)。
- `preserveDrawingBuffer:true` + `canvas.toDataURL` 取帧(不用 page.screenshot,
  避免把 DOM HUD 截进去)。

---

## 4. 目标仓库结构

```
bug-hunt-bench/
├── PLAN.md                    本文档
├── env/
│   ├── core.js                场景/物理/交互/__env API(ES module,importmap 引依赖)
│   ├── scenes.js              程序化几何构建器(env0 走廊、宝库房间、门/闸/拉杆/箱工厂)
│   ├── bugs.js                bug 注入器:输入配置 → 施加到场景(空气墙/穿模/门行为/...)
│   ├── human.html / agent.html
│   └── configs/
│       ├── env0-corridor.json
│       ├── env1-sponza-nav.json
│       ├── env2-sponza-2bugs.json
│       └── env3-buggy-world.json        含 bugs 数组与 answers(答案只被 eval 读)
├── harness/
│   ├── bridge.py              Playwright 封装:启动、GPU 检测、act/state/frames
│   ├── vlm.py                 OpenAI 兼容客户端(vLLM/OpenRouter 通用)
│   ├── policies/
│   │   ├── scripted.py        S0 冒烟 + S4 全覆盖轨迹策略
│   │   └── vlm_policy.py      prompt 构建、滚动上下文、动作解析
│   ├── tasks.py               任务定义(指令、目标、成功条件、预算)
│   └── runner.py              单 episode 执行 + 批量并行(episode 级并行,多 Chrome 实例)
├── eval/
│   ├── metrics.py             SR/误报/步数/blocked/打转/revisit;S2+ 的 P/R/定位误差
│   └── score_flags.py         flag ↔ answers 匹配(位置阈值 3m + 类型可选)
├── runs/                      输出(gitignore)
└── scripts/
    ├── check_gpu.sh           验证 headless Chrome 走真 GPU
    └── serve_model.sh         vLLM 启动命令集
```

不引入前端构建工具(vite/webpack)。保持 importmap + CDN + 静态服务,
`python -m http.server` 就能跑。这是刻意的简化,不要"优化"掉。

---

## 5. 环境 Setup(按序执行)

```bash
# 1. Python 侧
python3 -m venv .venv && source .venv/bin/activate
pip install playwright requests pillow numpy
playwright install chromium --with-deps

# 2. GPU 渲染验证(A6000)
bash scripts/check_gpu.sh
# 内部逻辑:headless Chromium 打开测试页,读 WEBGL_debug_renderer_info,
# 输出含 "A6000/NVIDIA" = 真 GPU;含 "SwiftShader/llvmpipe" = 软渲染。
# 软渲染也能跑通全流程(渲染不是瓶颈,VLM 推理才是),但要在日志里醒目标注。
# Chromium 启动参数基线(bridge.py 已含):
#   --no-sandbox --disable-dev-shm-usage --enable-webgl
#   --ignore-gpu-blocklist --use-angle=vulkan --enable-features=Vulkan
# 若拿不到 GPU:退路 A = xvfb-run + headed 模式;退路 B = 接受软渲染。

# 3. Docker 用户注意(不用 Docker 跳过)
# NVIDIA Container Toolkit 默认只给 compute,必须:
#   -e NVIDIA_DRIVER_CAPABILITIES=graphics,utility,compute
# 否则 EGL 初始化失败,Chrome 静默退回软渲染,极难排查。

# 4. vLLM(模型选型见 §7;Qwen3-VL 需要新版栈)
pip install -U vllm            # 需 >= 0.11
pip install -U "transformers>=4.57"
```

---

## 6. 已知坑清单(原型阶段用血换来的,必读)

1. **CORS**:多文件 glTF(Sponza)必须走 http,file:// 双击必挂。
2. **preserveDrawingBuffer**:不开则 toDataURL 拿到空白图,且不报错。
3. **材质共享**:glTF 多 mesh 共享 material,注入前必须 per-mesh clone,
   否则改一个全场变。
4. **DRACO/KTX2**:dungeon glb 是 DRACO 压缩,GLTFLoader 必须挂 DRACOLoader;
   将来换 Bistro 还要 KTX2Loader + MeshoptDecoder。
5. **SwiftShader 静默回退**:每次启动都要读 renderer 字符串并写进 run 日志。
6. **答案泄漏渠道**:answers JSON、beacons、helpers(V 键)、
   `window.__targets` 的语义命名。agent 入口一律不含;`__targets` 只在
   harness 判成功用,不进 prompt。
7. **传送门瞬移 vs "moved" 指标**:传送会产生一次巨大位移,统计路径长度时
   要把传送步的 moved 排除或单独记。
8. **实时物理 = 非确定性**:动作执行按真实时间片,同一 seed 两次轨迹不完全一致。
   当前接受;P2 有 sim-clock 重构任务。另外 `Math.random`(箱子朝向)要换成
   seeded RNG,seed 从配置进。
9. **速度向量水平污染**(已修复,防复发):移动是位置驱动时,碰撞滑动修正
   绝不能往 vel 写水平分量,否则无阻尼积累 → 永久漂移。vel 只承载竖直分量。
10. **Sponza 感知混叠**:中庭沿长轴近似对称,两端视觉几乎一样。这是导航
    任务的天然难点(保留,不修),分析轨迹时注意区分"迷路"与"混叠"。
11. **上下文爆炸**:每步带图,50 步左右超长。滚动窗口(近 3 步带图,更早转
    文字摘要)是下限方案,S3 长 episode 需要模型自维护"调查笔记"机制。
12. **地牢 mesh 无语义命名**:道具摆放靠 floorPoints() 地面扫描
    (网格射线 + 法线 + 头顶净空判定),不要假设 mesh 名字有意义。

---

## 7. 模型选型(A6000 环境)

约束:A6000 = 48GB / Ampere 架构。**Ampere 不支持 FP8** —— 一律避开 FP8
checkpoint,用 bf16 张量并行或 AWQ/GPTQ int4。

闭环 agent 的特殊考量:每个动作一次 VLM 调用,**解码延迟直接乘在 episode
时长上** → MoE 小激活模型(30B-A3B,激活仅 3B)每步快数倍,能跑更多 episodes,
是主力的合理选择。

| 角色 | 模型 | 卡数与精度 | 说明 |
|---|---|---|---|
| 管线调试 | Qwen3-VL-8B-Instruct | 1×A6000, bf16 | 快、便宜,S0/S1 冒烟用 |
| **主力** | **Qwen3-VL-30B-A3B-Instruct** | 2×A6000, bf16, TP2 | MoE 低延迟,当前开源 VLM 主线 |
| 主力备选 | Qwen3-VL-32B-Instruct(dense) | 2×A6000, bf16, TP2 | 与 30B-A3B 对照 |
| 大杯 | Qwen2.5-VL-72B-Instruct | 4×A6000, bf16, TP4(或 AWQ int4 2 卡) | 上一代但成熟稳定,栈兼容性最好 |
| 家族对照 | InternVL3.5-38B | 2×A6000, bf16, TP2 | 证明结论跨模型家族成立 |
| 可选尝鲜 | GLM-4.6V / Qwen3.5-Omni-30B | 视支持情况 | vLLM 支持成熟后再上 |

```bash
# scripts/serve_model.sh 示例
vllm serve Qwen/Qwen3-VL-30B-A3B-Instruct \
  --tensor-parallel-size 2 --max-model-len 32768 \
  --gpu-memory-utilization 0.92 --limit-mm-per-prompt image=4

vllm serve Qwen/Qwen2.5-VL-72B-Instruct \
  --tensor-parallel-size 4 --max-model-len 32768
```

注意:`--limit-mm-per-prompt` 要 ≥ 滚动窗口帧数(当前 3)+ interact 多帧(3)。
VLM 的图片 token 会显著撑大 KV cache,OOM 表现为请求超时而非显式报错,
排查时先降 max-model-len 和并发。

---

## 8. Coding Agent 任务清单

### P0 — 让 S0/S1 能跑(第一优先)
1. 仓库脚手架 + 本 PLAN.md 入库。
2. 从 buggy-world.html 拆出 env/core.js(场景无关的物理/交互/API)与
   scenes.js(几何构建);env3 配置化。**验收**:human.html 行为与原型一致
   (人工过一遍 9 个 bug)。
3. env0-corridor 构建器 + 配置。**验收**:agent.html?config=env0 加载 <2s。
4. agent.html(零 UI、自动 agentMode、URL 选配置)。**验收**:页面无
   answers/beacons 相关代码路径;截图帧无任何 UI 元素。
5. harness 重构(bridge/vlm/policies/tasks/runner 拆分)+ scripts/check_gpu.sh。
6. S0 冒烟脚本策略跑通 env0。**验收**:§2.3 S0 gate 全绿,产出 runs/ 样例。

### P1 — S1 实验
7. env1 配置(Sponza + 3 目标环);任务定义迁移(cyan/purple/gate 语义改为
   env1 的三个目标)。
8. metrics.py:SR、误报 done、步数、blocked、打转(累计同向转角 >360° 且
   位移 <1m)、revisit(2m 网格重访率);runner 批量模式(episode 级并行,
   每 Chrome 实例约 0.5-1GB 内存,16GB 主机开 6-8 并行)。
9. 出 S1 报告脚本:模型 × 任务 × proprio 的表格 + 逐 episode 轨迹俯视图
   (matplotlib 画 x-z 轨迹,叠目标点)。

### P2 — S2+ 与工程化
10. bugs.js 注入器:读配置施加 bug(从 bug-walk2.html 的 BUGS 注册表迁移);
    env2 配置。
11. score_flags.py:flag↔answer 位置阈值匹配 + clean 对照组误报统计。
12. sim-clock 重构:固定步长物理 + 虚拟时钟(门延迟等计时改虚拟时钟)+
    seeded RNG。**验收**:同 seed 同动作序列 → 逐帧一致。
13. Track P 管线:scripted 全覆盖轨迹 → 抽帧 → 批量 VLM 判读 → 同一套
    score_flags 评分。

---

## 9. 开放问题(留给实验数据决定,先按默认值做)

- proprio 默认 on 还是 off?(默认:两档都跑,作为主消融)
- 滚动窗口带几帧图?(默认 3;S3 再调)
- 动作粒度:forward 默认 1.5m、turn 默认 45° 是否合适?(S1 数据说话)
- flag 匹配半径 3m 是否合理?(S2 标定)
- 是否给画面叠罗盘?(默认不叠;S1 gate 不过再作为辅助项引入)
