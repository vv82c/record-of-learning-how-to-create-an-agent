"""agent_core — 累积式 Agent 的核心实现。

模块职责：
- config         路径常量
- llm            LLM 客户端与 OpenAI 协议消息适配
- memory         记忆存储（长期记忆 / 用户画像 / 历史 / 情景记忆）
- sessions       多会话管理（按会话隔离的全保真历史，/new /resume 的数据源）
- memory_compact 上下文压缩（history -> 记忆沉淀）
- memory_rag     长期记忆检索（Top-K 注入 system prompt）
- todos          TodoList 计划
- skills         技能加载
- tools          内置工具定义与执行
- registry       工具注册表（schema 与执行器统一登记与分发）
- subagent       子代理调度
- team           持久 Agent Team 与 inbox 消息总线
- mcp_client     MCP 外部工具协议
- hooks          Hook 生命周期框架与内置 Hooks
- runner         对话内核驱动器（SessionRunner：事件流 + confirmer 注入，终端/Web 双入口共用）

入口程序在项目根目录 main.py。
"""
