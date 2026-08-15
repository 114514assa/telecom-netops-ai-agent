from __future__ import annotations

import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient


class LangChainMCPBridge:
    """Expose this project's FastMCP server as LangChain-compatible tools.

    The main troubleshooting workflow remains deterministic and calls local domain services
    directly. This bridge is intentionally separate: it demonstrates MCP interoperability
    without handing diagnosis routing to an unconstrained ReAct loop.
    """

    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root or Path.cwd()).resolve()

    def build_client(self) -> MultiServerMCPClient:
        return MultiServerMCPClient(
            {
                "telecom-netops-readonly": {
                    "command": sys.executable,
                    "args": ["-m", "app.mcp_server"],
                    "cwd": str(self.project_root),
                    "transport": "stdio",
                }
            }
        )

    async def get_tools(self):
        client = self.build_client()
        return await client.get_tools()

    async def invoke(self, tool_name: str, arguments: dict | None = None):
        tools = await self.get_tools()
        tool = next((item for item in tools if item.name == tool_name), None)
        if tool is None:
            available = ", ".join(sorted(item.name for item in tools))
            raise KeyError(f"MCP tool {tool_name!r} not found; available: {available}")
        return await tool.ainvoke(arguments or {})
