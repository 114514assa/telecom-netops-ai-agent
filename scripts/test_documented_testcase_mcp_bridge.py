"""Optional real stdio MCP smoke test. Works without Ollama if RAG_ENABLED=false."""
import asyncio
from app.mcp_bridge import LangChainMCPBridge


async def run():
    bridge = LangChainMCPBridge()
    tools = await bridge.get_tools()
    names = sorted(tool.name for tool in tools)
    expected = {'list_document_grounded_testcases', 'generate_document_grounded_testcases', 'export_document_grounded_testcases'}
    missing = expected - set(names)
    if missing:
        raise RuntimeError(f'Missing MCP tools: {sorted(missing)}; registered={names}')
    # Tools can return MCP-normalized blocks, so check that invocation does not fail.
    summary = await bridge.invoke('list_document_grounded_testcases', {})
    cases = await bridge.invoke('generate_document_grounded_testcases', {'category': 'vlan', 'limit': 2})
    print('MCP discovery OK:', ', '.join(sorted(expected)))
    print('MCP category response:', str(summary)[:400])
    print('MCP testcase response:', str(cases)[:700])


if __name__ == '__main__':
    asyncio.run(run())
