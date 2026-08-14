.PHONY: install install-dev install-llm seed run test lint demo mcp model-info benchmark-quant clean

install:
	python -m pip install -r requirements.txt

install-dev:
	python -m pip install -r requirements-dev.txt

install-llm:
	python -m pip install -r requirements-llm.txt

seed:
	python scripts/seed_db.py

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q

lint:
	ruff check app scripts tests

demo:
	python scripts/run_demo.py --case vlan_mismatch

mcp:
	python -m app.mcp_server

model-info:
	curl http://127.0.0.1:8000/api/v1/system/model

benchmark-quant:
	python scripts/benchmark_quantization.py --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int8 int4

clean:
	rm -rf runtime .pytest_cache .ruff_cache
