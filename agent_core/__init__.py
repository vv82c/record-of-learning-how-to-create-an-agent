"""agent_core — 累积式 Agent 的核心实现。

模块职责：
- config         路径常量
- llm            LLM 客户端与 OpenAI 协议消息适配
- memory         记忆存储（长期记忆 / 用户画像 / 历史 / 情景记忆）
- memory_compact 上下文压缩（history -> 记忆沉淀）
- todos          TodoList 计划
- skills         技能加载
- tools          内置工具定义与执行
- subagent       子代理调度
- team           持久 Agent Team 与 inbox 消息总线
- mcp_client     MCP 外部工具协议
- hooks          Hook 生命周期框架与内置 Hooks

入口程序在项目根目录 main.py。
"""
