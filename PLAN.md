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

## 待评估想法（Backlog）

> 只记录，不排期。升级为正式任务前不占用主线资源。

- ~~`agent_core/llm.py` 的 `client` 是模块级单例~~ **已转正为阶段六 6.2 完成落地**
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
- 主循环单轮异常无兜底：4.5 开发中 remember() 的递归 bug 让 RecursionError 直接崩掉整个进程
  （1.4 只兜住了 LLM 调用段）；可加轮级 try/except，让单轮崩溃降级为报错后继续会话
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
