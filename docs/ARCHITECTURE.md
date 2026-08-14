# Architecture

## Design principle

The project separates **network-state judgement** from **language generation**. Interface/MAC/ARP/VLAN/resource consistency is parsed and diagnosed deterministically. RAG and LLM components are downstream aids for evidence retrieval and report organization.

## Workflow

1. Normalize incident input.
2. Query the simulated access-resource inventory by terminal IP.
3. Parse terminal/switch evidence.
4. Run deterministic diagnosis rules.
5. Retrieve relevant local runbook chunks with TF-IDF.
6. Compose a complete deterministic Markdown report.
7. Optionally reorganize the report using either an OpenAI-compatible LLM or a local Hugging Face model.
8. Pause for human approval with LangGraph `interrupt`.
9. Resume by `thread_id`, archive the report, and append audit events.

## Local model path

The local Hugging Face backend is lazy-loaded only when `LLM_ENABLED=true` and `LLM_BACKEND=local_hf`. It supports:

- default precision;
- CUDA FP16;
- bitsandbytes INT8;
- bitsandbytes INT4/NF4 with double quantization.

A backend load/generation failure is non-fatal: the system falls back to the deterministic report template and preserves the diagnostic result.

## Safety controls

- simulated/RFC1918 data only;
- input size validation;
- no production credentials;
- no SSH/Telnet device connector;
- no network write commands;
- deterministic diagnosis before LLM;
- constrained report prompt;
- human approval before archive;
- JSONL audit trail;
- model configuration endpoint exposes no API key.
