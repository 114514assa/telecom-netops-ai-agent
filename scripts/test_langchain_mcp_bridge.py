from __future__ import annotations

import asyncio

from app.mcp_bridge import LangChainMCPBridge


async def main() -> None:
    bridge = LangChainMCPBridge()
    tools = await bridge.get_tools()
    print("LangChain MCP tools:")
    for tool in tools:
        print(f"- {tool.name}: {tool.description}")

    result = await bridge.invoke("get_readonly_boundary", {})
    print("\nReadonly boundary result:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
