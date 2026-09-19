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

- 项目已通过全量代码分析并推送 GitHub：`vv82c/record-of-learning-how-to-create-an-agent`
- 阶段一~四（16 项）已全部完成（2026-08-23）；阶段五（3 项）源于 oxalpha 实战复盘
- Backlog 现存 7 条改进候选（沙箱、轮级异常兜底等，见文末）

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
| 5.1 失败预算 | 熔断模式、"带原因的失败"设计 | 能说清熔断阈值为什么是"连续"而非"累计" |
| 5.2 子代理日志 | 可观测性、结构化事件日志 | 能只凭日志复盘一次失败的派遣 |
| 5.3 错误文案 | 面向模型的错误设计（错误消息也是提示词） | 能举出一条好错误消息如何改变模型行为 |

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
- [x] **4.4 记忆检索（RAG）**（✅ 2026-08-23，实测：123 条 → 403 条记忆，system prompt 恒定 2002 字；注入块仅全量 2%；123 条中埋的双事实端到端全部答对；mock 验证 API 向量路径与降级路径。注：DeepSeek 无 embeddings 接口，默认本地词法向量，换供应商后 .env 配 LLM_EMBEDDING_MODEL 即可切换语义检索）
  - 要求：长期记忆不再全量塞 system prompt，改为向量化按需检索 Top-K
  - 【完成标志】MEMORY.md 膨胀到 100 条以上时，单轮请求的 system prompt 体积保持稳定
- [x] **4.5 多会话管理**（✅ 2026-08-23，单测 6/6：隔离、全保真往返、悬空修复、列表、路径穿越；跨进程端到端：/resume 恢复 4 条旧会话并正确续答，懒创建无孤儿文件。开发中修掉两个自产 bug：replace_all 误伤 remember 定义致无限递归；/resume 精确匹配漏掉带参调用）
  - 要求：history.jsonl 按会话 ID 隔离；支持 `/new` 开新对话、`/resume` 恢复历史会话
  - 【完成标志】两个会话的对话记录互不混杂，`/resume` 能找回并继续旧会话
- [x] **4.6 人格可配置（persona）**（✅ 2026-08-23，单测 6/6：能力块两套人格下逐字节一致（1856字）、回退安全；端到端：太监/管家双人格声音切换、read_file 行为一致、/persona 运行时切换生效。**至此 16 项任务全部完成**）

## 阶段五：容错与可观测（P4 — 源于 2026-08-23 oxalpha 实战复盘）

> 起因：让 Agent 收集 Ox Alpha 跑分信息，两个东厂子代理双双烧满回合失败且无原因可查。
> 诊断依据：memory/sessions/20260823-235615.jsonl——主因是未挂代理导致大量目标站超时
> （openrouter/algolia/bing 可达，duckduckgo/xcancel/ycombinator/archive 全超时的典型墙内直连特征）；
> 代码侧三个放大器让失败"不可止损、不可归因、不引导换策略"，本阶段逐项修复。

- [x] **5.1 子代理失败预算（熔断）与带原因回传**（✅ 2026-08-24，实测：三个不可达地址第一轮即熔断，总耗时 34s 远小于 15 回合，回传含"连续 3 次"原因与建议；正常 echo 任务不受影响）
  - 要求：run_subagent 连续 N 次（默认 3，env `AGENT_SUBAGENT_FAIL_BUDGET`）工具失败即提前收兵；
    熔断与轮数上限的回传都必须带原因与统计，替换"未能在限定回合内办妥差事"固定串
  - 【完成标志】构造只能失败的任务（抓取不可达地址 192.0.2.x），子代理在远小于回合上限时收兵，
    回传包含"连续 N 次"失败字样；正常任务（echo 一类）不受影响
- [x] **5.2 子代理执行日志落盘**（✅ 2026-08-24，单测：start/tool/end 事件结构完整；集成：熔断任务日志含 3 条失败 tool 事件与 outcome=circuit_breaker，正常任务 outcome=done）
  - 要求：每次派遣把 start / tool / end 事件写入
    `memory/subagent_logs/<时间>-<身份>-<随机>.jsonl`，含每次工具调用成败与结果摘要、
    最终 outcome（done / circuit_breaker / max_turns）
  - 【完成标志】一次熔断任务跑完后日志文件存在、事件完整可解析、outcome=circuit_breaker；
    正常任务 outcome=done
- [x] **5.3 web_fetch 错误文案与策略提示**（✅ 2026-08-24，单测 5/5：DNS 失败独立文案且不再冒充 SSRF 拦截、内网拦截回归不变、超时附换源提示、正常抓取不误伤。**至此阶段五完成，累计 19 项任务**）
  - 要求：DNS 解析失败不再误标为"SSRF 防护已拦截"（独立文案）；连接超时的错误信息
    附带"疑似网络受限，建议换可达源"提示，引导模型自行换源
  - 【完成标志】不存在的域名 → 文案含"主机名解析失败"且不含"SSRF"；127.0.0.1 仍为
    SSRF 拦截文案；不可达 IP（192.0.2.1）超时 → 文案含换源提示；正常外网抓取不受影响
  - 要求：太监总管人格抽出为 `templates/persona/*.md`，可切换
  - 【完成标志】切换 persona 文件后重启，Agent 以新人设对话，工具行为不变

---

## 阶段六：模型配置中心（P5 — 2026-09-03 立项，Backlog 首条转正）

- [x] **6.1 配置层 model_profiles.py**（✅ 2026-09-03，实测：.env 自动种子为首个档案；upsert 空 api_key 沿用旧值；activate/delete 语义正确；`model_profiles.json` 先行入 .gitignore——含 Key 与 .env 同级敏感）
  - 要求：多模型档案（name/base_url/api_key/model/context_window）+ 活跃档案，存项目根 JSON；.env 齐备时自动种子迁移，此后 .env 退化为兜底
  - 【完成标志】load/upsert/activate/delete 单元断言全过；配置文件被 gitignore 挡住（check-ignore 验证）
- [x] **6.2 llm client 运行时重建**（✅ 2026-09-03，Backlog 首条转正落地。实测：apply_profile 重建 client 后热切换跑真实对话成功；apply_profile(None) 后 call_llm 发"未配置模型"引导错误不崩溃；终端 main.py 回归正常）
  - 要求：client/MODEL/CONTEXT_WINDOW 变为可重建模块属性；全部调用方（runner/subagent/team/memory_rag/main）从 `from .llm import client` 改为 `llm.client` 属性引用（引用焊死则换配置不可见）；context_window 随档案走（E5 账房直接受益）
  - 【完成标志】切换档案后 MODEL/窗口随档案变化且真实对话成功；重复 apply_profile 幂等；全部模块 import 与终端回归通过

## 阶段七：人性化交互（P6 — 2026-09-03 立项，对标市面 agent 体验）

- [x] **7.1 save_memory 工具与压缩可见化**（✅ 2026-09-03，实测：模型对"请记住…"主动调用 save_memory，内容入 MEMORY.md 且 RAG 索引哈希自动重建；压缩触发时发 memory_compacted 事件，UI 通知"已沉淀入卷宗"。system prompt 增补第 10 条行事规矩）
  - 【完成标志】端到端："请记住：朕偏好简短回复"→ 工具卡 save_memory 出现、记忆文件含该条；registry 单条注册零分发改动（4.1 的活体证明第二例）
- [x] **7.2 会话自动命名**（✅ 2026-09-03，实测：第一轮 done 后微型 LLM 调用起 ≤10 字标题（"天蓝圣旨答"），session_title 事件驱动偏殿名册刷新；resume 后不重复命名；终端 /resume 列表同步受益）
  - 【完成标志】标题落盘 titles.json（list_sessions 只扫 *.jsonl 不误列）；无 title 回退首条消息预览；命名失败静默不影响对话
  - 【坑】推理模型把小 max_tokens 全花在思维链上导致正文为空——命名调用上限放宽到 1024
- [x] **7.3 另拟 / 改旨**（✅ 2026-09-03，实测：regenerate 回滚到最后一条真实用户消息（跳过 Stop 门禁提醒）重跑，history 与会话文件 truncate 续写后全程一致；edit_last 换问重跑；UI 侧显示与历史对齐（回滚后收走屏上旧问旧答））
  - 【完成标志】另拟后历史条数不变、回复不同；改旨后最后一条用户消息被替换；会话文件条数 == history 条数；_last_real_user_index 跳过门禁提醒
- [x] **7.4 思维链流式转发**（✅ 2026-09-03，实测：deepseek-v4-flash 推理 174 条 reasoning 事件全程捕获，不写入 history、不计入回复；前端"圣思"折叠段答完自动收起）
  - 【完成标志】reasoning_start/reasoning 事件先于 reply_start；_consume_stream 读 delta.reasoning_content；reasoning 不污染 history 与 token 统计口径

## 阶段八：会话管理与导出（P7 — 2026-09-06 立项，UI 侧见 UIPLAN.md 阶段 H）

- [x] **8.1 SessionStore 会话管理**（✅ 2026-09-06，实测：delete_session 连文件/轮转备份/titles/custom 一并清除（复用 _path 的穿越防护），rename_session 写 custom_titles.json 标记手动题名，`_maybe_title` 见 custom 即弃写——手动命名不被自动题名覆盖；list_sessions(query) 题名+全文不区分大小写检索，轮转 .bak 不混入名册）
  - 【完成标志】内核断言 10 项：检索大小写不敏感、改名后检索联动、导出含圣谕/奏对/奉差且无 tool 回执、删除后题名文件干净、备份不进检索
- [x] **8.2 会话 REST 与终端命令**（✅ 2026-09-06，实测：/api/sessions?q= 检索、rename/delete（delete 对 ACTIVE_SESSIONS 中当值偏殿回 409——防"办差中的殿被拆后 runner 续写致文件静默重建"）、/api/sessions/export Markdown 下载；终端 /find 检索、/export [会话ID] 誊出话本到 exports/）
  - 【完成标志】REST 错误分支全验（空题名 400 / 未知会话 404 / 当值删除 409 / 重复删除 404）；终端命中/未命中/缺省三分支全过

## 阶段九：内务府——统一设置中心（P8 — 2026-09-06 立项，UI 侧见 UIPLAN.md 阶段 I）

- [x] **9.1 app_settings.py 设置层**（✅ 2026-09-06，实测：settings.json 用户层覆盖 .env 种子层，损坏/缺失静默回落；save 走 _validate 强校验（类型收敛 + 区间 5~600 秒 / 1~10 次 + 未知键与未知人格拒绝）；**上下文窗口刻意不收编**——它是模型档案属性，随档案切换（阶段六），全局设只会与模型阁打架）
  - 【完成标志】内核断言 6 项：种子回落、save/load 往返、区间外全拦截、未知键/人格拒绝、损坏文件回落、部分提交只动提交项
- [x] **9.2 消费点运行时生效**（✅ 2026-09-06，实测：三个消费点全部改为使用时现读——runner 建连时读 default_persona（settings 覆盖 AGENT_PERSONA env）、WSConfirmer 建连时读 ask_timeout（subagent 熔断预算每次派遣现读 _fail_budget()）；改设置零重启）
  - 【完成标志】save 后新建 SessionRunner 人格变 guanjia、_fail_budget()==5、load()["ask_timeout"]==30 三证齐；REST：GET/POST /api/settings（校验错转 400）、终端 /settings 查看；浏览器圣旨弹窗实测倒计时按颁行后的 60 秒计时（高危档 + Esc 驳回全链路）

## 阶段十：Hook 收编——三执行体统一守卫（P9 — 2026-09-19 立项，Backlog"子代理绕过 Hook 链"转正）

> 背景：Hook 链此前只存在于 `SessionRunner.dispatch_tool`，子代理（`execute_basic_tool` 直调）
> 与队友（registry 直查）全部绕过——敏感文件拦截、危险命令拦截、审计、输出截断对他们失效；
> 通传小黄门可 `type .env` 绕过主循环的 deny。本阶段把链下沉到注册表统一守卫入口，
> 三端一次收编；主循环行为零变化（断言取证），子代理/队友获得防护是**有意变更**。

- [x] **10.1 统一守卫入口 `registry.execute_guarded`**（✅ 2026-09-19，Hook 链 + 执行 + 事件全内聚；on_event/confirmer 参数化；ask 无确认者时 fail-closed 降级为 deny；保住 server.py 的"先发 hook_ask 再等确认"时序契约）
  - 【完成标志】主循环 `dispatch_tool` 收缩为"调守卫入口 + todos 事件"；事件名与字段（hook_ask/hook_decision/tool_start/tool_end 含 blocked/ok/duration_ms）与收编前逐字段一致（断言 7a~7c）；临时计数 Hook 证明 before_tool_call 单次触发（7d）；浏览器圣旨弹窗正常弹出 + Esc 驳回，时序契约实证
- [x] **10.2 子代理与队友接入**（✅ 2026-09-19，subagent 换 execute_guarded（函数内延迟导入避开循环 import——team.py 先例）；team._exec 同改；confirmer=None 走 fail-closed；审计条目增 sender 字段，收掉子代理/队友写操作的审计盲区）
  - 【完成标志】内核断言：守卫四分支（deny / ask 准 / ask 驳 / ask 无确认者）、写路径沙箱改写落盘、输出截断标记、审计 sender 入账、队友 `_exec` 读 .env 被拒（10a，此前可静默读走）
- [x] **10.3 熔断计数兼容**（✅ 2026-09-19，`_is_tool_failure` 增计 "[HookDecision: 拒绝/阻止]" 前缀——被策略拦等于差事推进不了，计入连续失败，防子代理对拒绝死循环烧回合）
  - 【完成标志】`_is_tool_failure` 四态断言（Error ✓ / 拒绝 ✓ / 阻止 ✓ / 正常输出 ✗）
- [x] **10.4 验证与收尾**（✅ 2026-09-19，四轨全过：内核断言 **25 项全绿**；终端 /settings 冒烟；REST 4 项 200（health/静态页/settings/sessions）；浏览器真跑——派通传小黄门读 .env，两度触 .env 命令均被 fail-closed 拒绝、回执入出巡簿（ok:false 计熔断口径）、主对话诚实回禀**零泄漏**、子代理日志与审计 sender 可归因；主循环 git commit 高危圣旨弹窗照常弹出、Esc 驳回链路完整。已知取舍留痕：内官监营造的 pip install/git commit 类高危 ask 收编后自动拒绝，若实际受挫，后续可在内务府加"子代理 ask 策略"设置）

## 阶段十一：轮级异常兜底——主循环安全网（P10 — 2026-09-19 立项，Backlog"主循环单轮异常无兜底"转正）

> 背景：`_run_loop` 的 while 体没有 try/except——模型吐坏 JSON 参数（`llm.to_tool_call` 的
> `json.loads`，流式拼回的 arguments 被 max_tokens 截断即残缺）、MCP 子进程与磁盘意外都会穿透：
> 终端直接崩进程（4.5 的 remember() 递归事故即此形态）；Web 界面虽被 server 线程接住不崩，
> 但工具批中途炸会留下"assistant 带 tool_calls 而无配对 tool 消息"的悬空历史（且已落盘），
> 下一轮请求被 API 400 打回、轮轮如此——一个坏参数放大成一个会话的死刑。
> 本阶段两层网 + 一个终端护栏，让单轮崩溃降级为"报错后继续会话"。

- [x] **11.1 协议保对**（✅ 2026-09-19，`_parse_tool_blocks` 逐个解析 message.tool_calls：单条解析失败 / 参数非 JSON 对象 → 以该 id 就地落一条 Error tool 消息并跳过，同批其余照常执行；批后回填循环改为按 message.tool_calls 顺序覆盖全部 id）
  - 【完成标志】断言 A1~A5：残缺 JSON 收到 Error tool 消息、同批 current_time 不受牵连照常执行、每个 tool_call_id 都有配对、轮次正常收尾零 error 事件（fake call_llm 全链路，不烧真 token）
- [x] **11.2 轮级兜底**（✅ 2026-09-19，`_finish_round` 包住 `_run_loop`；`_crash_landing` 先发 error 事件、再 `_patch_dangling_tool_calls` 补尾部悬空并落盘、拼 assistant 说明入史后正常走 done，落点自身全程防御；send/regenerate/edit_last 各加入口级网护序备段；顺手修正 `_assistant_say` 为"先落盘再改内存史"——断言 D3 抓到落盘失败时内存史残留半截状态的问题）
  - 【完成标志】断言 B1~B5（call_llm 抛异常→收束文案/error+done 事件入列/尾部 assistant 说明/会话文件无悬空）、C1~C3（半批悬空恰好补缺失 id 且幂等）、D1~D3（remember 打炸→入口网收束不二次崩）
- [x] **11.3 终端护栏**（✅ 2026-09-19，main.py REPL 的 `runner.send` 包 try/except，终端获得与 Web 线程同级的"进程不死"保障）
  - 【完成标志】终端 /settings + 退出冒烟干净
- [x] **11.4 验证与收尾**（✅ 2026-09-19，内核断言 **16 项全绿** + 终端/REST 冒烟（health/静态页 200）+ 浏览器正常轮真跑（"现在几点"→current_time 工具卡 ✓、报时正确、自动题名、零错误）；债⑤子代理 LLM 裸奔的爆炸半径被本网收窄——其独立的重试/回禀增强仍留 Backlog）

## 阶段十二：命令出访确认——SSRF 纵深的 ask 兜底层（P11 — 2026-09-19 立项，Backlog"curl 绕过 SSRF"第一层）

> 背景：SSRF 防护只护 web_fetch 的 HTTP 客户端，`run_command` 执行 curl/Invoke-WebRequest
> 可直达内网/云元数据（端到端实测中 Agent 自己提出这条"绕行建议"）。根治靠命令级沙箱
> （容器 `--network none` 方案，见 Backlog）；本阶段先上便宜的兜底：网络出访类命令走圣旨
> 确认（level=confirm，与敏感路径同构），子代理/队友等无确认者语境 fail-closed 自动拒绝。
> 已知边界：黑名单拦不住变体编码，本质是"把把关人换皇上"而非围墙。

- [x] **12.1 EGRESS_PATTERNS 出访模式表**（✅ 2026-09-19，curl/wget/invoke-webrequest/invoke-restmethod/iwr /nc /ssh /scp /sftp /ftp /telnet/urllib/requests.get/socket.socket/certutil -urlcache/bitsadmin /transfer，大小写不敏感子串匹配；检查位次插在 HIGH_SENSITIVITY 之后——既有危险/敏感/高危三类的分类行为零变化）
  - 【完成标志】内核断言 13 项全绿：curl/大写 CURL/Invoke-WebRequest/urllib/certutil 五类出访命中 ask(confirm)、`echo hello` 不误伤、`git commit` 仍走高危 ask、`type .env` 仍走敏感 ask、危险命令仍 deny、子代理 curl 自动拒绝（阶段十 fail-closed 语义衔接）、准奏后 `curl --version` 照常执行
- [x] **12.2 验证与收尾**（✅ 2026-09-19，浏览器真跑：传旨"用 curl 访问 http://192.168.1.1"→ 模型拼出 `curl -s -i -m 10 http://192.168.1.1 | head -50` 照样被子串匹配逮住、圣旨弹窗亮"网络出访"文案（昼间素绢主题目检）、Esc 驳回链路完整、主对话诚实回禀、自动题名「访问路由器请求被拦截」；SUMMARY 补纵深条目；根治路径（容器沙箱）留 Backlog 不动）

## 待评估想法（Backlog）

> 只记录，不排期。升级为正式任务前不占用主线资源。

- ~~`agent_core/llm.py` 的 `client` 是模块级单例~~ **已转正为阶段六 6.2 完成落地**
- ~~子代理与队友的工具调用走 `execute_basic_tool`，不经过 Hook 链~~ **已转正为阶段十完成落地**
- `subagent.py` 的 `run_subagent` 内 LLM 调用无兜底（team.py 已有 try/except）：
  子代理内 API 抛错会击穿主循环，建议复用 1.4 的 `call_llm`
- `run_command` + `curl http://192.168.1.1` 可绕过 web_fetch 的 SSRF 防护（端到端实测中
  Agent 主动提出了这条"绕行建议"）——**阶段十二先落 ask 兜底层**（出访命令走圣旨确认）；
  根治仍靠命令级沙箱/出网白名单（容器 `--network none` 方案待立项）
- 批量工具调用中若有一个被 Hook 拦截，整轮直接终止，同批其余**成功**的结果也不向用户/模型汇报
  （4.1 端到端实测发现：current_time 成功 + read .env 被拒，最终只见拒绝）——
  可改为逐个回传结果，让模型继续汇报未受阻的部分
- ~~主循环单轮异常无兜底：4.5 开发中 remember() 的递归 bug 让 RecursionError 直接崩掉整个进程
  （1.4 只兜住了 LLM 调用段）；可加轮级 try/except，让单轮崩溃降级为报错后继续会话~~
  **已转正为阶段十一完成落地**
- 工具 schema 的 description 里仍带人设用语（"派遣一个小太监"等，registry.py），未随 persona
  切换——修改 schema 描述可能影响模型的工具选择行为，4.6 未动；可评估把描述中性化，
  人设术语全部收进 persona 模板的用语表

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
| 2026-08-23 | 任务 4.4 完成并勾选：新增 `agent_core/memory_rag.py`（可插拔向量源 + 阈值混合策略 + 内容哈希缓存），build_system_prompt 按当前话题检索注入 | 阶段四推进；供应商 DeepSeek 无 embeddings 接口（探测 404），默认本地 bigram 词法向量并保留 env 一键切换语义检索的通道 |
| 2026-08-23 | 任务 4.5 完成并勾选：新增 `agent_core/sessions.py`（全保真会话存储 + 协议修复 + 懒创建），/new /resume 接入主循环；新增 1 条 Backlog（轮级异常兜底） | 阶段四推进；开发中两次踩坑并修复：replace_all 把 remember 定义体内的调用一并替换致无限递归（989 条重复写入后崩溃）；/resume 用精确匹配导致带参命令落入聊天路径，模型自己翻文件"假恢复"造成端到端假绿灯 |
| 2026-08-23 | 任务 4.6 完成并勾选，**阶段四全部完成，16 项任务清零**：persona 模板化（taijian/guanjia）、系统提示词人设能力分离、/persona 运行时切换、AGENT_PERSONA 默认值；新增 1 条 Backlog（schema 描述人设用语） | 全计划收官；验证采用"能力块逐字节一致"的最强不变性标准 |
| 2026-08-24 | 新增阶段五（5.1~5.3）并更新基线；同日 oxalpha 实战诊断：主因未挂代理致目标站超时，放大器为子代理无熔断、无日志、错误不引导换源 | 实战暴露的问题按纪律先入计划再修复 |
| 2026-08-24 | 任务 5.1/5.2/5.3 完成并勾选，**阶段五完成，累计 19 项**：熔断实测 34s 收兵（对比烧满 15 回合）、子代理日志可归因、DNS/SSRF 文案分离与超时换源提示 | oxalpha 三大放大器全部拆除；测试断言自身也曾数错文件数（单测记录器与集成共用目录），按 purpose 字段修正校验 |
| 2026-08-24 | 新增 [UIPLAN.md](UIPLAN.md)：Emperor Agent 前端计划书（阶段 A-D 共 12 项，FastAPI + 零构建前端 + pywebview 壳，只绑 127.0.0.1） | 软件化方向立项；UI 子系统单独成计划，本文件继续作为 agent_core 的路线基准 |
| 2026-09-03 | 新增阶段七并完成（7.1~7.4 人性化交互，对标市面 agent）：save_memory 工具 + 压缩事件；会话自动命名（titles.json + session_title 事件）；另拟/改旨（send 抽出 _finish_round，regenerate/edit_last + sessions.truncate + 跳过门禁提醒）；思维链流式转发（reasoning_content → 事件，不入 history）。前端配合见 UIPLAN 阶段 G。内核断言 7 项 + 浏览器全流程 + 终端回归全过 | 用户确认按"记忆存在感 > 自动命名 > 另拟改旨 > 圣思"优先级落地；踩坑：推理模型小 max_tokens 全花在思维链上致命名正文为空——上限放宽；list_sessions 曾因缩进错误只返回一个会话，浏览器验收抓到 |
| 2026-09-03 | 新增阶段六并完成（6.1 配置层 + 6.2 client 运行时重建，Backlog 首条转正）：model_profiles.py 多档案配置（.env 自动种子迁移、空 key 沿用旧值、model_profiles.json 先行入 .gitignore）；llm.py 改 apply_profile 可重建，runner/subagent/team/memory_rag/main 全部改 llm. 属性引用；context_window 随档案走。内核断言（切换/幂等/未配置引导/空 key 沿用）+ 终端回归全过 | 用户需求"模型配置放软件里"：配置界面属 UIPLAN 阶段F，内核侧的配置层与可重建 client 是其前置，一并落地 |
| 2026-09-06 | 新增阶段八并完成（8.1 SessionStore 管理 + 8.2 会话 REST 与终端命令，UI 侧见 UIPLAN 阶段 H）：delete/rename/search/export 四能力进 SessionStore，rename 记 custom_titles 防 _maybe_title 覆盖；ACTIVE_SESSIONS 当值守卫（删除回 409）；/find /export 进终端。回归验收四轨全过（内核断言 10 项 / REST 8 项含错误分支 / 终端 4 分支 / 浏览器 14 项），顺手修复前端驻留条关闭钮监听器漏写 | 用户指令"回测第一档并更新文档推送"：回测即全量回归，无新 bug，仅补文档留痕 |
| 2026-09-06 | 新增阶段九并完成（9.1 app_settings 设置层 + 9.2 消费点运行时生效，UI 侧见 UIPLAN 阶段 I 内务府面板）：settings.json 覆盖 .env 种子、强校验、损坏回落；ask_timeout/default_persona/subagent_fail_budget 三旋钮使用时现读零重启；上下文窗口不收编（归模型阁档案）。内核断言 6 项 + REST + 终端 /settings + 浏览器颁行与弹窗倒计时联动全过 | 第二档第一项"统一设置面板"：F3 模型阁趟出的 JSON+REST+表单模式直接复用，.env 从此只是种子；settings.json 入 gitignore（机器本地偏好） |
| 2026-09-19 | 新增阶段十并完成（10.1~10.4，Backlog"子代理绕过 Hook 链"转正）：Hook 链从 runner.dispatch_tool 下沉至 registry.execute_guarded 统一守卫入口，主循环/子代理/队友三端一次收编；ask 无确认者 fail-closed 降级为 deny；审计条目增 sender；熔断计数兼容 Hook 拒绝。内核断言 25 项全绿 + 终端/REST 冒烟 + 浏览器真跑（小黄门读 .env 被 fail-closed 拦截零泄漏、主循环圣旨弹窗 Esc 驳回无回归） | 审计与策略防护对子代理/队友全盲区（通传小黄门可 type .env 绕主循环 deny）；收编后消除未来双触发隐患，主循环行为零变化由断言取证 |
| 2026-09-19 | 新增阶段十一并完成（11.1~11.4，Backlog"主循环单轮异常无兜底"转正）：11.1 协议保对（坏 JSON 参数就地回 Error tool 消息，历史永无悬空）；11.2 轮级兜底（_finish_round 安全网：悬空补对→error 事件→说明入史→正常 done，入口级网护序备段，落点自身全程防御）；11.3 终端护栏（REPL 包 try/except 进程不死）。内核断言 16 项全绿（fake call_llm 全链路）+ 终端/REST 冒烟 + 浏览器正常轮真跑；断言抓到并修正 _assistant_say"先改史后落盘"的半截状态问题 | 模型吐坏参数（流式 arguments 截断）/MCP 与磁盘意外穿透主循环：终端崩进程（4.5 事故形态）、Web 会话悬空后轮轮 400——一个坏参数放大成一个会话的死刑 |
| 2026-09-19 | 新增阶段十二并完成（12.1~12.2，Backlog"curl 绕过 SSRF"第一层）：ToolPolicyHook 增 EGRESS_PATTERNS 出访模式表（16 模式），命中走 ask(level=confirm)，无确认者语境 fail-closed 自动拒绝；根治（容器沙箱）另立项。内核断言 13 项全绿 + 浏览器真跑（curl 摸 192.168.1.1 被圣旨拦下、Esc 驳回、零实际出网） | SSRF 防护只护 web_fetch 窄口子，run_command 出网工具可直达内网/云元数据；先上便宜兜底把把关人换成皇上，黑名单拦不住变体的边界如实留痕 |
