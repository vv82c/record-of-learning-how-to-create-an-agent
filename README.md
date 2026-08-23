# create_an_agent — 累积式 Agent 学习实践

我在学习 AI Agent 开发过程中完成的实践项目：基于 OpenAI 兼容接口的 function calling，在终端里从零实现一个对话 Agent。它复刻了 Claude Code 的核心架构，跑起来后 AI 会以"大内太监总管"的口吻侍奉"皇上"（你）。

## 🙏 致谢

本项目是在学习 **TheSyart** 的开源项目 [claude-agent-examples](https://github.com/TheSyart/claude-agent-examples)，以及 B 站 UP 主 **"小单说AI"** 的系列教学视频之后，跟随其讲解逐模块理解，并在此基础上完成整理的初步研究。

非常感谢原作者的无私分享，让我这样一个初学者能够系统地理解 Agent 的核心设计。强烈推荐去看原仓库和原视频：

- GitHub：<https://github.com/TheSyart/claude-agent-examples>
- Bilibili：搜索 UP 主 **"小单说AI"**

本仓库仅作为个人学习记录。

## ✨ 实现了什么

- **工具调用**：读/写文件、执行命令、抓网页、glob/grep 搜索、加载技能（统一注册表，一处注册全端可用）
- **三层记忆 + 上下文压缩**：长期记忆 `MEMORY.md`、用户画像 `USER.md`、每日情景记忆；对话过长时自动把旧消息沉淀进记忆文件
- **长期记忆 RAG 检索**：记忆按当前话题检索 Top-K 注入，system prompt 体积与记忆总量解耦
- **TodoList 计划**：多步骤任务先拆计划再逐步执行
- **技能系统**：从 `skills/` 目录加载 `SKILL.md`（YAML frontmatter）
- **子代理调度**：5 种预设身份（按工具白名单分级授权），支持并发派遣；连续失败自动熔断收兵，执行日志落盘可归因
- **持久 Agent Team**：有名有姓的队友线程 + 文件收件箱消息总线；队友上下文自动压缩防膨胀
- **MCP 外部工具**：长连接复用子进程、断线自动重连
- **Hooks 生命周期**：Event → Matcher → Handler → Decision 四层模型，内置安全策略（敏感文件管控/危险命令拦截/SSRF 防护）、审计日志、输出截断、Stop 质量门禁
- **流式输出**：回答逐 token 上屏，工具调用碎片按 index 拼装
- **多会话管理**：`/new` 开新会话、`/resume` 跨进程恢复；会话全保真存储
- **人格可配置**：`templates/persona/*.md` 模板化人设，`/persona` 运行时切换

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 在项目根目录创建 .env（已被 .gitignore 忽略，不会上传）
# LLM_BASE_URL=你的 OpenAI 兼容接口地址
# LLM_API_KEY=你的 API Key
# LLM_MODEL=模型名称

# 3. 运行
python main.py
```

可选：在根目录放置 `mcp_servers.json` 接入外部 MCP 工具（同样不会上传）。

## 📁 项目结构

```
PLAN.md               # 完善计划书：19 项任务的验收标准、勾选纪律与变更记录
SUMMARY.md            # 学习总结：知识点、自测题（含参考要点）、踩坑实录、验证方法学
LEARNING.md           # 个人学习笔记与阶段复盘
main.py               # 主入口：REPL 主循环、工具分发、子代理并发调度
agent_core/
  ├─ llm.py           # LLM 客户端与 OpenAI 消息适配
  ├─ tools.py         # 内置工具定义与执行（含 SSRF 防护）
  ├─ registry.py      # 工具注册表：schema 与执行器统一登记
  ├─ memory.py        # 记忆存储
  ├─ memory_compact.py# 上下文压缩
  ├─ memory_rag.py    # 长期记忆 Top-K 检索
  ├─ sessions.py      # 多会话管理（全保真存储与恢复）
  ├─ todos.py         # TodoList 计划
  ├─ skills.py        # 技能加载
  ├─ subagent.py      # 子代理调度（熔断 + 执行日志）
  ├─ team.py          # 持久团队与消息总线
  ├─ mcp_client.py    # MCP 客户端（长连接）
  └─ hooks.py         # Hook 生命周期框架
templates/            # 提示词模板（记忆压缩、人格 persona 等）
examples/             # 示例：最小 MCP Server
memory/               # 运行时记忆数据（不上传，自动生成）
```
