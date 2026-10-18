"""Check the PDF MCP tool via the genuine local stdio MCP client (needs MCP deps)."""
import asyncio
import base64
from pathlib import Path
from app.mcp_bridge import LangChainMCPBridge


async def main():
    sample = Path('tests/fixtures/documented_interface_excerpt.pdf')
    tools = await LangChainMCPBridge().get_tools()
    names = [t.name for t in tools]
    print('MCP tools:', names)
    if 'extract_pdf_document' not in names:
        raise RuntimeError('PDF MCP tool not registered')
    result = await LangChainMCPBridge().invoke('extract_pdf_document', {
        'pdf_base64': base64.b64encode(sample.read_bytes()).decode('ascii')
    })
    print(str(result)[:900])
    if 'GigabitEthernet0/0/15' not in str(result):
        raise RuntimeError('PDF MCP returned no expected text')
    print('PASS: PDF MCP tool discovery and stdio invocation')


if __name__ == '__main__':
    asyncio.run(main())
