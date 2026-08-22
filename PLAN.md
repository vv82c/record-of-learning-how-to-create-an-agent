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
- [ ] **1.3 创建 requirements.txt**
  - 内容：`openai`、`python-dotenv`、`pyyaml`、`mcp`
  - 同步：README 快速开始一节改为 `pip install -r requirements.txt`
  - 【完成标志】在一个全新目录 `git clone` 本仓库后，仅执行 `pip install -r requirements.txt`
    并配置 `.env`，`python main.py` 能正常启动进入对话
- [ ] **1.4 主循环 LLM 调用异常兜底**
  - 位置：`main.py` 中 `client.chat.completions.create(...)`（约 378 行）
  - 要求：try/except 捕获 API 异常；打印错误信息后**返回输入提示符继续会话**，不崩溃退出；
    可选加分项：指数退避自动重试 2~3 次（仅对超时/限流类错误）
  - 【完成标志】故意把 `.env` 中 API Key 改错后运行，程序打印错误但不退出，
    仍能继续输入；改回正确 Key 后无需重启即可恢复对话

## 阶段二：安全加固（P1）

- [ ] **2.1 read_file 纳入策略 Hook 管控**
  - 位置：`agent_core/hooks.py` 的 `ToolPolicyHook`
  - 要求：matcher 扩展为 `write_file|run_command|read_file`；读取命中
    `SENSITIVE_PATTERNS`（.env、id_rsa、credentials 等）时返回 deny
  - 【完成标志】对 Agent 说"读取 .env 文件"，工具返回 `[HookDecision: 拒绝]` 开头的消息，
    文件内容不出现在对话与 history 中
- [ ] **2.2 run_command 加固**
  - 要求一：`subprocess.run` 增加 `timeout`（建议 120 秒），超时返回错误文本
  - 要求二：`DANGEROUS_PATTERNS` 补充 Windows 等价命令
    （`Remove-Item -Recurse`、`del /s /q`、`format `、`rd /s` 等）
  - 【完成标志】① 执行 `python -c "import time; time.sleep(999)"` 在 120 秒被截断并返回
    超时错误；② 执行 `Remove-Item -Recurse` 类命令被 Hook 拒绝
- [ ] **2.3 web_fetch 内网防护（防 SSRF）**
  - 位置：`agent_core/tools.py` 的 `web_fetch`
  - 要求：解析目标主机名，拒绝 localhost、127.0.0.1、0.0.0.0、
    192.168.0.0/16、10.0.0.0/8、172.16.0.0/12、169.254.0.0/16
  - 【完成标志】让 Agent 抓取 `http://127.0.0.1` 与 `http://192.168.1.1`，
    均返回拒绝提示而非发起请求

## 阶段三：修 Bug 与体验（P2）

- [ ] **3.1 修复主 Agent 缺 `list_mcp_servers` schema 的 bug**
  - 位置：`main.py` 的 `TOOLS` 列表（系统提示词提到了该工具但 schema 缺失）
  - 【完成标志】配置一个可用的 MCP Server 后，主 Agent 调用 `list_mcp_servers`
    能成功返回 server 与工具清单
- [ ] **3.2 流式输出**
  - 要求：主循环改用 `stream=True`，回答逐 token 打印到终端（工具调用阶段可不流式）
  - 【完成标志】提一个需要长回答的问题，终端逐步显示文字，而非整段一次性出现
- [ ] **3.3 新增斜杠命令 `/todos`、`/memory`、`/compact`**
  - 要求：`/todos` 打印当前计划；`/memory` 打印 MEMORY.md 与 USER.md 内容；
    `/compact` 手动触发一次上下文压缩
  - 【完成标志】三条命令在 REPL 中输入后各自生效，且不影响原有 `/team` `/inbox` `/mcp`

## 阶段四：架构演进（P3 — 长线，单项可拆分为独立迭代）

- [ ] **4.1 工具注册表化**
  - 要求：schema 与执行器绑定注册（name → handler 映射），替代 `execute_main_tool`
    的 if/elif 长链和 main.py 内联的 6 个 schema
  - 【完成标志】新增一个演示工具只需在注册表加一条记录，无需改动分发逻辑；
    现有全部工具行为不变
- [ ] **4.2 队友线程接入 memory_compact**
  - 要求：`team.py` 队友的 `messages` 超阈值时复用压缩机制，防止上下文无限膨胀
  - 【完成标志】构造 40+ 轮队友对话场景，队友 messages 长度被压回阈值附近且仍能正常回禀
- [ ] **4.3 MCP 长连接**
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

- （暂无）

---

## 变更记录

| 日期 | 变更内容 | 原因 |
|---|---|---|
| 2026-08-22 | 创建计划书；1.1、1.2 直接标记完成 | 依据当日分析报告与已完成工作 |
| 2026-08-22 | 新增【学习路线】章节与 LEARNING.md，使用规则增补第 6 条 | 学习者要求边开发边学习，将知识点与开发任务逐一绑定 |
