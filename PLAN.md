# 完善计划书（PLAN.md）

> **本文件是本项目后续开发的唯一路线基准。**
> 目的：实时比对开发进度，防止路线漂移和"幻觉式完工"。
> 创建日期：2026-08-22 ｜ 依据：2026-08-22 完成的全项目分析报告

---

## 📏 使用规则（每次开发会话必须遵守）

1. **会话开始**：先通读本文件，明确当前进度，只做"下一个未勾选"的任务。
2. **勾选纪律**：每完成一项，立即把 `- [ ]` 改为 `- [x]` 并注明完成日期。勾选的唯一依据是该项的
   **【完成标志】逐条核实通过**，不能凭"感觉做完了"。
3. **改动留痕**：新增、修改、删除任何任务，必须在文末【变更记录】登记一行。
4. **新想法隔离**：临时想到的方向一律先进【待评估想法（Backlog）】，评估后再升级为正式任务，
   严禁直接插入主线。
5. **会话结束**：更新勾选状态后随代码一起 commit，保持仓库与本文件同步。
6. **学习同步**：每勾选一个开发任务，必须同步在 [LEARNING.md](LEARNING.md) 用自己的话写一条学习笔记；
   知识是否学会，以"能不看资料讲给别人听"为标准（详见下方【学习路线】）。

---

## 当前基线

- 项目已通过全量代码分析（14 个源码文件，约 2269 行，语法检查全部通过）
- 已推送至 GitHub：`vv82c/record-of-learning-how-to-create-an-agent`（commit `ea2a21c`）
- 已确认的待修 bug：主 Agent 缺 `list_mcp_servers` 工具 schema（见 3.1）

---

## 🎓 学习路线（与开发任务绑定，边做边学）

**总原则：做一项，学一块。** 每完成一个开发任务，同步搞懂它背后的知识与技巧；
检验标准是"能输出"——能不看资料把原理讲给别人听，才算学会（费曼学习法）。

| 开发任务 | 背后的知识点 | 学会的检验方式 |
|---|---|---|
| 1.1 / 1.2（已完成） | Markdown 文档、git 基础与 .gitignore | 能独立完成 init → add → commit → push 全流程 |
| 1.3 依赖清单 | pip / venv 依赖管理与环境隔离 | 不看资料在新机器上搭好运行环境 |
| 1.4 异常兜底 | LLM API 调用模式、异常处理、重试与退避 | 能讲清"为什么一次 API 失败不能毁掉整个会话" |
| 2.1 read_file 管控 | Agent 权限模型、最小权限原则 | 能画出一次工具调用要经过的 Hook 检查链 |
| 2.2 命令加固 | 命令注入、黑名单 vs 白名单、沙箱思想 | 能举出三种绕过黑名单的方式 |
| 2.3 内网防护 | SSRF 原理、内网地址段划分 | 能解释 Agent 场景下 SSRF 的攻击面 |
| 3.1 schema 修复 | function calling 协议（schema 与模型行为的关系） | 能解释模型为什么调不出没给 schema 的工具 |
| 3.2 流式输出 | 流式协议、chunk 拼接处理 | 能说清流式与整段返回的差异和实现要点 |
| 3.3 斜杠命令 | REPL 交互设计 | 能不看教程独立新增一条命令 |
| 4.1 注册表化 | 注册表模式、开放封闭原则 | 能说清它比 if/elif 长链好在哪里 |
| 4.2 队友压缩 | 上下文工程、token 预算意识 | 能估算一个队友线程跑 N 轮的 token 消耗 |
| 4.3 MCP 长连接 | MCP 协议、stdio 传输、进程生命周期 | 能画出一次 MCP 调用的时序图 |
| 4.4 记忆 RAG | 嵌入向量、相似度检索、Top-K | 能说清"全量注入"与"检索注入"的取舍 |
| 4.5 多会话 | 会话状态设计 | 能设计出会话隔离的数据结构 |
| 4.6 persona | 提示词工程、人设与能力分离 | 能换一个人设而不破坏任何工具行为 |

**学习纪律**（防"做完就忘"）：
1. 每勾选一个开发任务，当天在 LEARNING.md 追加一条笔记（模板见该文件）。
2. 笔记必须用自己的话写；写不出来 = 还没懂，回代码里再读一遍。
3. 每完成一个阶段，写一次阶段复盘（哪些真懂了、哪些还虚）。

**推荐资源**：
- 原项目与教程：[TheSyart/claude-agent-examples](https://github.com/TheSyart/claude-agent-examples)、
  B 站"小单说AI"系列视频（本项目的基础）
- OpenAI 官方文档：Function Calling、Streaming 章节
- Anthropic 官方博客：《Building effective agents》等 Agent 设计文章
  （本项目的架构思想源自 Claude Code，读原文能加深理解）
- MCP 官方文档：modelcontextprotocol.io

---

## 阶段一：工程化底座（P0 — 最高优先级）

- [x] **1.1 编写 README.md**（含致谢、快速开始、项目结构）
  - ✅ 完成于 2026-08-22，commit `ea2a21c`
- [x] **1.2 编写 .gitignore 并初始化 git 仓库、首次推送**
  - ✅ 完成于 2026-08-22，已验证 `.env` / `memory/` / `templates/USER.md` / `.team/` 均被拦截
- [x] **1.3 创建 requirements.txt**（✅ 2026-08-22，按完成标志验证：全新 clone + 独立 venv 安装 + 启动成功）
  - 内容：`openai`、`python-dotenv`、`pyyaml`、`mcp`
  - 同步：README 快速开始一节改为 `pip install -r requirements.txt`
  - 【完成标志】在一个全新目录 `git clone` 本仓库后，仅执行 `pip install -r requirements.txt`
    并配置 `.env`，`python main.py` 能正常启动进入对话
- [x] **1.4 主循环 LLM 调用异常兜底**（✅ 2026-08-22，实测：错误 Key 得 401 不崩溃、回到提示符；正确 Key 重启后恢复正常对话）
  - 位置：`main.py` 中 `client.chat.completions.create(...)`（约 378 行）
  - 要求：try/except 捕获 API 异常；打印错误信息后**返回输入提示符继续会话**，不崩溃退出；
    可选加分项：指数退避自动重试 2~3 次（仅对超时/限流类错误）
  - 【完成标志】故意把 `.env` 中 API Key 改错后运行，程序打印错误但不退出，
    仍能继续输入；改回正确 Key 并**重启**后恢复正常对话
    （2026-08-22 修订：原标准"无需重启恢复"不可达——client 在进程启动时读取 .env，
    运行中修改不生效；动态重建 client 已列入 Backlog）

## 阶段二：安全加固（P1）

- [x] **2.1 read_file 纳入策略 Hook 管控**（✅ 2026-08-22，单测 12/12 + 端到端实测：Agent 读 .env 被拒，history 中密钥出现 0 次）
  - 位置：`agent_core/hooks.py` 的 `ToolPolicyHook`
  - 要求：matcher 扩展为 `write_file|run_command|read_file`；读取命中
    `SENSITIVE_PATTERNS`（.env、id_rsa、credentials 等）时返回 deny
  - 【完成标志】对 Agent 说"读取 .env 文件"，工具返回 `[HookDecision: 拒绝]` 开头的消息，
    文件内容不出现在对话与 history 中
- [x] **2.2 run_command 加固**（✅ 2026-08-22，实测：sleep(999) 在 120.4 秒被截断、进程树无残留；Windows 危险命令单测 20/20；敏感路径命令走 ask）
  - 要求一：`subprocess.run` 增加 `timeout`（建议 120 秒），超时返回错误文本
  - 要求二：`DANGEROUS_PATTERNS` 补充 Windows 等价命令
    （`Remove-Item -Recurse`、`del /s /q`、`format `、`rd /s` 等）
  - 【完成标志】① 执行 `python -c "import time; time.sleep(999)"` 在 120 秒被截断并返回
    超时错误；② 执行 `Remove-Item -Recurse` 类命令被 Hook 拒绝
- [x] **2.3 web_fetch 内网防护（防 SSRF）**（✅ 2026-08-23，单测 34/34：CIDR 边界、拦截列表、域名指向内网、重定向检查、外网不误伤；端到端实测 Agent 抓 127.0.0.1 与 192.168.1.1 均被拒）
  - 位置：`agent_core/tools.py` 的 `web_fetch`
  - 要求：解析目标主机名，拒绝 localhost、127.0.0.1、0.0.0.0、
    192.168.0.0/16、10.0.0.0/8、172.16.0.0/12、169.254.0.0/16
  - 【完成标志】让 Agent 抓取 `http://127.0.0.1` 与 `http://192.168.1.1`，
    均返回拒绝提示而非发起请求

## 阶段三：修 Bug 与体验（P2）

- [x] **3.1 修复主 Agent 缺 `list_mcp_servers` schema 的 bug**（✅ 2026-08-23，配置 FastMCP demo server 端到端实测通过；连带修复 mcp 2.0.0 下 `tool.inputSchema` → `input_schema` 的潜伏 AttributeError，并新增 `examples/demo_mcp_server.py` 供复现）
  - 位置：`main.py` 的 `TOOLS` 列表（系统提示词提到了该工具但 schema 缺失）
  - 【完成标志】配置一个可用的 MCP Server 后，主 Agent 调用 `list_mcp_servers`
    能成功返回 server 与工具清单
- [x] **3.2 流式输出**（✅ 2026-08-23，采样验证：长回答输出文件呈 9 个增长台阶逐步上屏而非一次跳变；多轮工具调用回归：连续 5 轮流式拼装 tool_calls 执行正常，无重复打印）
  - 要求：主循环改用 `stream=True`，回答逐 token 打印到终端（工具调用阶段可不流式）
  - 【完成标志】提一个需要长回答的问题，终端逐步显示文字，而非整段一次性出现
- [x] **3.3 新增斜杠命令 `/todos`、`/memory`、`/compact`**（✅ 2026-08-23，端到端实测三条命令生效；/compact 无可压时返回明确提示；/team /inbox /mcp 零回归）
  - 要求：`/todos` 打印当前计划；`/memory` 打印 MEMORY.md 与 USER.md 内容；
    `/compact` 手动触发一次上下文压缩
  - 【完成标志】三条命令在 REPL 中输入后各自生效，且不影响原有 `/team` `/inbox` `/mcp`

## 阶段四：架构演进（P3 — 长线，单项可拆分为独立迭代）

- [x] **4.1 工具注册表化**（✅ 2026-08-23，以新增 current_time 工具验证"注册表单条记录即全端可用、零分发改动"；单测 12/12，端到端模型主动调用新工具，Hook/队友白名单/MCP 回归全过）
  - 要求：schema 与执行器绑定注册（name → handler 映射），替代 `execute_main_tool`
    的 if/elif 长链和 main.py 内联的 6 个 schema
  - 【完成标志】新增一个演示工具只需在注册表加一条记录，无需改动分发逻辑；
    现有全部工具行为不变
- [x] **4.2 队友线程接入 memory_compact**（✅ 2026-08-23，单元：41 条合成历史压至 11 条且共享记忆零污染；集成：真实队友线程 18 条传话/13 次回禀，水位曲线 22→10 两次、压缩后仍正常回禀并优雅关闭）
  - 要求：`team.py` 队友的 `messages` 超阈值时复用压缩机制，防止上下文无限膨胀
  - 【完成标志】构造 40+ 轮队友对话场景，队友 messages 长度被压回阈值附近且仍能正常回禀
- [x] **4.3 MCP 长连接**（✅ 2026-08-23，spy 计数实测：10 次调用 + list_tools 仅 spawn 1 次进程；杀进程模拟断线后自动重连（spawn=2）恢复调用；stop/退出零残留进程）
  - 要求：`MCPClient` 保持 stdio 会话而非每次 `call_tool` 冷启动子进程
  - 【完成标志】连续调用同一 MCP 工具 10 次，进程只启动一次；连接断开时自动重连或降级报错
- [ ] **4.4 记忆检索（RAG）**
  - 要求：长期记忆不再全量塞 system prompt，改为向量化按需检索 Top-K
  - 【完成标志】MEMORY.md 膨胀到 100 条以上时，单轮请求的 system prompt 体积保持稳定
- [ ] **4.5 多会话管理**
  - 要求：history.jsonl 按会话 ID 隔离；支持 `/new` 开新对话、`/resume` 恢复历史会话
  - 【完成标志】两个会话的对话记录互不混杂，`/resume` 能找回并继续旧会话
- [ ] **4.6 人格可配置（persona）**
  - 要求：太监总管人格抽出为 `templates/persona/*.md`，可切换
  - 【完成标志】切换 persona 文件后重启，Agent 以新人设对话，工具行为不变

---

## 待评估想法（Backlog）

> 只记录，不排期。升级为正式任务前不占用主线资源。

- `agent_core/llm.py` 的 `client` 是模块级单例，启动时读取 .env；如需"改 Key / 换模型免重启"，
  须重构为运行时可重建，并把各模块的 `from .llm import client` 统一改为 `llm.client` 引用
- `subagent.py` 的 `run_subagent` 内 LLM 调用无兜底（team.py 已有 try/except）：
  子代理内 API 抛错会击穿主循环，建议复用 1.4 的 `call_llm`
- 子代理与队友的工具调用走 `execute_basic_tool`，**不经过** `execute_main_tool` 的 Hook 链——
  2.1/2.2 的 Hook 层防护（敏感文件、危险命令）对他们不生效；只有做在工具函数内部的
  SSRF 防护（2.3）能覆盖全端。可选方案：把关键防护下沉到工具层，或让子代理也接入 Hook 注册表
- `run_command` + `curl http://192.168.1.1` 可绕过 web_fetch 的 SSRF 防护（端到端实测中
  Agent 主动提出了这条"绕行建议"）——命令黑名单不认识它；根治靠命令级沙箱/出网白名单
- 批量工具调用中若有一个被 Hook 拦截，整轮直接终止，同批其余**成功**的结果也不向用户/模型汇报
  （4.1 端到端实测发现：current_time 成功 + read .env 被拒，最终只见拒绝）——
  可改为逐个回传结果，让模型继续汇报未受阻的部分

---

## 变更记录

| 日期 | 变更内容 | 原因 |
|---|---|---|
| 2026-08-22 | 创建计划书；1.1、1.2 直接标记完成 | 依据当日分析报告与已完成工作 |
| 2026-08-22 | 新增【学习路线】章节与 LEARNING.md，使用规则增补第 6 条 | 学习者要求边开发边学习，将知识点与开发任务逐一绑定 |
| 2026-08-22 | 任务 1.3、1.4 完成并勾选（均按完成标志实测验证） | 阶段一推进 |
| 2026-08-22 | 修订 1.4 完成标志（"无需重启恢复"→"重启后恢复"）；新增 2 条 Backlog | 原标准与架构现状冲突：client 启动时读取 .env，运行中修改不生效；验证中发现 subagent 缺兜底 |
| 2026-08-22 | 任务 2.1 完成并勾选（单测 12/12 + 端到端实测，history 零密钥泄漏）；新增 1 条 Backlog | 阶段二推进；验证中发现 run_command 存在绕过路径 |
| 2026-08-22 | 任务 2.2 完成并勾选；Backlog"run_command 绕过读取保护"升级并入 2.2（命令涉及敏感路径走 ask）；顺手修复大小写绕过（_match_pattern 改为大小写不敏感） | 阶段二推进；首版超时实现在 Windows 存在管道死锁（孙进程持有管道写端），改为临时文件中转 + taskkill 整树击杀后实测通过 |
| 2026-08-23 | 任务 2.3 完成并勾选，**阶段二（安全加固）全部完成**；新增 2 条 Backlog（子代理绕过 Hook 链、curl 绕过 SSRF） | 阶段二收官；端到端实测中 Agent 自己演示了"建议用 curl 绕关防"，佐证纵深防御的必要性 |
| 2026-08-23 | 任务 3.1 完成并勾选；连带修复 `mcp_client.build_tool_schemas` 的 `inputSchema` 兼容 bug；新增 `examples/demo_mcp_server.py` | 阶段三推进；验证暴露两层潜伏 bug——schema 缺失导致工具不可调，字段名不兼容导致配置 MCP 后启动即崩，均为"从未真正执行过的代码路径" |
| 2026-08-23 | 任务 3.2 完成并勾选 | 阶段三推进；验证方法学：采样输出文件增长曲线证明"逐步上屏"，多轮工具调用验证 chunk 拼装正确性 |
| 2026-08-23 | 任务 3.3 完成并勾选，**阶段三（修 Bug 与体验）全部完成**；compact_history 新增 force 参数 | 阶段三收官；实测中自动压缩在对话内自然触发两次，/compact 的无操作反馈路径亦得到验证 |
| 2026-08-23 | 任务 4.1 完成并勾选：新增 `agent_core/registry.py` 统一注册；main.py 删内联 schema 与 if/elif 分发链，team.py 接入注册表（函数内导入破循环依赖）；新增演示工具 current_time；新增 1 条 Backlog | 阶段四推进；端到端发现"批量调用一个被拦即整轮终止"的既有交互问题 |
| 2026-08-23 | 任务 4.2 完成并勾选：compact_history 新增 update_memory_files / episode_prefix 参数（队友只追加 episode，不回写共享记忆），队友工作循环末尾接入压缩 | 阶段四推进；写入权限分级是本项核心设计：队友视角片面，全量重写会冲掉主 Agent 记忆 |
| 2026-08-23 | 任务 4.3 完成并勾选：MCPClient 改长连接（专职后台事件循环承载会话，懒建立 + 断线丢弃重连 + atexit 清理） | 阶段四推进；解决 async 会话与同步多线程 Agent 的桥接问题 |
