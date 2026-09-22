# 与 ZCode 开源代码的一次比较学习——借鉴指南

> **性质**：2026-09-21 与 [zai-org/ZCode](https://github.com/zai-org/ZCode)（Z.ai 官方 agent harness，
> v3.14.0，Apache-2.0，约 84 万行 TypeScript）做的一次**比较学习**，不是开发任务。
> 本文是学习产物与后续优化指引；候选条目已按老规矩挂入 PLAN.md【待评估想法（Backlog）】，
> 升级转正时以本文对应章节为设计输入，动代码之前先改 PLAN.md。
>
> **配套材料**（同目录）：`repo/` 官方源码浅克隆（commit 872ad96，`git pull` 可更新）；
> `架构分析.md` 仓库全貌；`_raw/` 定位仓库时的检索留痕。克隆与 `_raw` 已入 .gitignore 不入库。

---

## 一、方法：为什么这次比较可信

一方是 4733 行的 Python 个人项目，一方是 84 万行的企业仓库，体量差 178 倍。比较的价值
不在"谁的方案好"，而在**独立收敛**：两个互不知情的团队（一个 solo、一条产品线）在同类
问题上做出了同样的设计决策，就说明这些决策是承重墙而非时尚；反过来，**不一样的地方，
恰好标出了"规模逼出来的结构"**——那就是个人项目的候选路线图。

## 二、独立收敛对照表（先给自己记一功）

| 本项目已有 | ZCode 对应 | 备注 |
| --- | --- | --- |
| `llm.py` RETRYABLE_ERRORS + 指数退避 1s→2s（十四⑤） | `adapters/src/model/runner.ts` 重试/空闲超时 | 连"重试必须收口在唯一模型接缝"的结构判断都一致 |
| ToolPolicyHook `EGRESS_PATTERNS` 出访模式表（十二） | `core/src/tool/handlers/webfetch-egress-guard.ts` + bash 只读判定表 | **局限结论逐字同构**："黑名单拦不住变体编码，根治靠沙箱" |
| 圣旨 ask 确认 + 无确认者 fail-closed（十/十二） | `core/src/permission/broker.ts` + approval-gate | 同款把关人模式 |
| 密折临时对话不留痕（十三） | ephemeral session（runner 随连接生灭） | 同款产品判断 |
| 11.1 协议保对 + `_patch_dangling_tool_calls` | 悬空 tool call 补齐 | 同款不变量：历史永无悬空 |
| 十四③批量拦截后注入防重试提醒继续循环 | 合成消息注入（system-reminder 同构） | 同款"给模型递纸条"手法 |
| fake call_llm 断言测试（不烧真 token） | `fs-fault-injection.ts` 假件/故障注入测试 | 同款测试文化 |
| PLAN/SUMMARY/UIPLAN/LEARNING/README 五文档同维护 | AGENTS.md / DESIGN.md / CONTEXT.md spec-first 治理 | 同款"文档即 AI 系统提示词" |
| 一套 runtime 喂终端 + Web + REST | 一套内核喂 TUI / Web / Desktop | 同款薄壳结构 |

## 三、五条可借鉴（按性价比排序，前三条可立项）

### 借鉴A 圣旨规则持久化（permission rules as data）

- **ZCode 做法**：`packages` 内 `core/src/permission/` 三件套（broker / service /
  `rule-matching.ts`），allow/deny 规则**落盘持久化**（permission-rules-persistence），
  同类操作第二次不再重复弹窗；Bash 另有独立的只读判定表
  （`bash-readonly-policy-*.ts`）——危险等级当**数据表**维护，不散落在 if 里。
- **本项目现状**：`hooks.py` 的 ToolPolicyHook 每次现场判断，圣旨每单必奏，重复操作
  重复打扰。
- **建议落点**：hooks.py 增规则记忆层。要点：
  1. 优先级 **deny > ask > allow**（deny 永不被 allow 覆盖）；
  2. 规则记"模式"（命令前缀/工具名+参数模式）而非全量命令文本，防止把一次性的
     恶意参数固化成永久豁免；
  3. 准奏弹窗可带"记住此类操作"选项；审计照记（规则命中也要留痕）。
- **验收思路**：同一命令第二次不弹圣旨 + 审计条目含"规则命中"标记 + 提供
  查看/清除规则的途径（settings 或命令）。

### 借鉴B 子代理只读预设（Explore 型 profile）

- **ZCode 做法**：`core/src/subagent/` 子代理 = profile 定义（frontmatter），其中
  Explore 型只配 Read/Bash 搜索类工具，专做侦察不落笔——所有主流 harness 验证过的
  安全模式。
- **本项目现状**：`subagent.py` / `team.py` 无"角色→工具白名单"维度。
- **建议落点**：run_subagent 增 profile 参数（工具白名单 + 系统提示词变体）。只读
  侦察兵可免奏（白名单内全是只读工具）。**与阶段十的收编成果完全兼容**：白名单是
  `registry.execute_guarded` 前的一道过滤，Hook 链照走不绕。
- **验收思路**：只读预设子代理尝试 run_command 被注册表拦截并如实回禀；派遣普通
  任务行为零变化（断言取证，照抄阶段十手法）。

### 借鉴C 微压缩（microcompact）

- **ZCode 做法**：`core/src/compact/policy.ts` 两级上下文管理——autocompact 阈值
  之前先做 microcompact：把老轮次的**工具输出**截断/替换为占位（保 tool call 骨架、
  丢内容），推迟昂贵的整体总结。
- **本项目现状**：`memory_compact.py` 水位触发轮末自动压缩，一步到位。
- **建议落点**：压缩流程加前置层。要点：
  1. **红线**：占位替换必须保持消息结构合法（tool_use/tool_result 配对 id 保留、只换
     content，assistant/tool 不悬空）——正是 11.1 用血换来的不变量，微压缩不得破坏它；
  2. 最近 N 轮不碰（近期工具输出最常被引用）；
  3. 只动"出旨给模型"的内容，`history.jsonl` 磁盘留痕保持原文（审计完整性优先，
     与密折阶段确立的"审计照记"同一原则）。
- **验收思路**：长会话水位曲线实验（对比压缩触发点推迟多少）+ 压缩后模型仍能
  答对早期事实（骨架保留的价值取证）。

### 借鉴D 异常即状态迁移（心智模型，不立项）

- **ZCode 做法**：`core/src/agent/turn-machine.ts` 显式状态机
  （ProcessingInput→ModelRequest→Streaming→ScheduleTools→ExecutingTools→Permission→
  Aggregating→Complete/Fail），每个异常都是有名有姓的状态迁移。
- **本项目现状**：`runner._run_loop` + `_finish_round` 防御网（十一）已是症状级
  修复，够用。
- **结论**：4733 行不需要状态机重构。借的是**心智模型**：每加一层防御网时问一句
  "这个异常对应哪个状态迁移"，给异常命名，让网越织越有序而不是越织越乱。日后若
  会话形态变复杂（并行轮/工作流），再评估显式状态机。

### 债② 根治的分层印证（充实既有条目，不新增）

ZCode 自己对"命令出访/子进程"的答案也是分层的，与十二阶段的判断互相印证：

1. **出访黑名单**（务实第一层）——本项目十二已落地同款；
2. **Windows Job Object 管子进程生死**（MCP 子进程用 job object 绑定）——可作
   容器方案落地前的**过渡层**：pywin32 可调，把 run_command / MCP 的子进程树绑进
   Job Object（限内存/一荣俱荣一损俱损），比等 Docker Desktop 依赖便宜得多；
3. **远程 workspace 直接跑在容器里**（harness/remote 就是那个 SSH 测试容器）——
   印证 ② 容器 `--network none` 仍是根治方向不变。

建议：② 立项时把 Job Object 作为中间档一并评估（内务府三档"宿主/自动/强制"的
"自动"档可先落 Job Object）。

## 四、明确不抄清单（个人 agent 的竞争力在薄）

- RPC 分层（VS Code 式 IPC，`packages/rpc`）、插件市场 CDN 分发、手机远控的
  owner/lease 路由、`formal-proof` 状态空间验证器、`model-option-map` CEL 表达式
  编译器——全部为多用户/多设备/企业遥测服务，4733 行的项目背不动也不需要背。
- 但有一个**姿态**值得抄：ZCode 对未开源的 CUA 直接给 fail-closed 空壳包 + NOTICE
  里明说边界。本项目未来未落地的能力面（如 memory_rag 的语义检索源）照此办理：
  接口先立、明说未实现、调用时给引导文案而非假装可用。

## 五、使用方式

1. Backlog 三条候选（A/B/C）已挂 PLAN.md【待评估想法】，评估通过后转正立项，
   以本文对应章节为设计输入；
2. 借鉴D 是设计原则，日后续写 LEARNING.md 时可并入；
3. 债② 的 Job Object 中间层在 ② 立项时一并评估；
4. 佐证代码在 `repo/`，本文引用的 ZCode 路径均相对仓库根，可直接检索对照。
