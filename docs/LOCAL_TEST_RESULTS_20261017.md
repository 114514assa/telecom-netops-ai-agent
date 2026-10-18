# Offline verification record — 2026-10-17

Checked in the assistant's restricted Linux build container (NOT the user's Windows .venv):

- `python -m compileall -q app scripts tests`: completed.
- `python -m pytest -q tests/test_grounded_testcase_tools.py tests/test_document_grounding.py tests/test_parsers.py tests/test_diagnosis.py tests/test_hardening_network.py tests/test_repository.py tests/test_pdf_ingest.py tests/test_grounded_testcase_api.py`: **31 passed, 1 skipped**.
- The API contract test module was **skipped** because the build container has no `langgraph` dependency. Windows environment has reported LangGraph installed, but these new API tests must still be run there.
- `python -m scripts.export_document_grounded_cases --validate-only`: 34 curated cases; referenced knowledge files/section titles present.
- No Ollama, Qwen INT4, Hugging Face inference, full LangGraph + HITL, external MCP stdio server, nor DeepSeek E2E was rerun.

All test outputs for newly generated cases start with `verification_state=not_executed`. Provenance descriptions are labels from the curated source dataset, not a fresh independent reading of original PDF content.
