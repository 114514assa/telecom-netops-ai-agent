# Architecture

## Design principle

The project separates **network-state judgement** from **language generation**. Interface/MAC/ARP/VLAN/resource consistency is parsed and diagnosed deterministically. LangChain RAG and optional LLM generation are downstream aids only.

## Workflow

1. Normalize incident input with Pydantic models.
2. Query the simulated access-resource inventory by terminal IP.
3. Parse terminal/switch evidence.
4. Run deterministic diagnosis rules.
5. Build a semantic retrieval query from structured evidence.
6. Retrieve local runbook chunks through LangChain `OllamaEmbeddings` + FAISS.
7. Compose a complete deterministic Markdown report.
8. If LLM is enabled, use LangChain `ChatPromptTemplate` to create a constrained auxiliary prompt and pass it to the configured backend.
9. Validate the auxiliary sentence with application guardrails; reject it on any safety/consistency failure.
10. Pause for human approval with LangGraph `interrupt`, then resume by `thread_id` and archive the report.

## LangChain / LangGraph / MCP separation

- **LangGraph** owns workflow state, node ordering, conditional routing, interrupt/resume and checkpointing.
- **LangChain** owns prompt composition, Document/vector-store abstractions and Ollama embedding integration.
- **MCP/FastMCP** exposes the read-only domain capabilities as protocol tools.
- **langchain-mcp-adapters** provides an interoperability path that loads those MCP tools as LangChain tools.
- The primary troubleshooting graph intentionally calls deterministic Python domain services directly instead of using an unconstrained ReAct loop.

## Safety controls

- simulated/RFC1918 data only;
- no production credentials or device connector;
- no network write commands;
- deterministic diagnosis before RAG/LLM;
- RAG fail-open: retrieval failure does not change diagnosis;
- constrained LangChain prompt + post-generation guardrail;
- human approval before archive;
- SQLite checkpoint + JSONL audit trail.
