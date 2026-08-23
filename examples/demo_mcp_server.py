"""examples/demo_mcp_server.py — 最小 MCP Server 示例（任务 3.1 验证用，也是学习样例）。

MCP server 的本质：一个通过 stdio 收发 JSON-RPC 的进程，对外声明两件事——
  list_tools：告诉客户端"我有哪些工具"（名称、描述、参数 schema）
  call_tool ：真正执行一次工具调用

本地体验方法：在项目根目录创建 mcp_servers.json（该文件已被 .gitignore 忽略）：

{
  "servers": {
    "demo": {
      "command": "python",
      "args": ["examples/demo_mcp_server.py"],
      "enabled": true
    }
  }
}

然后从项目根目录运行 python main.py，输入 /mcp 即可看到本 server 及其工具。
"""
import asyncio

from mcp.server.mcpserver import MCPServer

server = MCPServer("demo")


@server.tool()
def echo(text: str) -> str:
    """原样返回输入的文本（演示用）"""
    return f"echo: {text}"


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
