# Local LLM Quantization

## Why quantization exists in this project

The network diagnosis path is deterministic: parsers and rules decide interface/MAC/VLAN/resource consistency. The local LLM is only an optional report-language backend. Quantization is included as a reproducible engineering experiment for comparing local inference resource cost, not as a claim that a quantized model improves diagnosis accuracy.

## Supported modes

- `none`: model default precision.
- `fp16`: half-precision CUDA inference.
- `int8`: bitsandbytes 8-bit weight loading.
- `int4`: bitsandbytes 4-bit NF4 weight loading with double quantization.

The implementation uses Hugging Face `AutoModelForCausalLM` and `BitsAndBytesConfig`. Actual hardware support and speedups depend on the selected model, accelerator, driver, PyTorch, Transformers and bitsandbytes versions.

## Install

```bash
pip install -r requirements-llm.txt
```

## Enable local quantized report generation

```env
LLM_ENABLED=true
LLM_BACKEND=local_hf
LOCAL_LLM_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
LOCAL_LLM_QUANTIZATION=int4
LOCAL_LLM_DEVICE_MAP=auto
```

Start the service normally:

```bash
python scripts/seed_db.py
uvicorn app.main:app --reload
```

Inspect the non-secret model configuration:

```bash
curl http://127.0.0.1:8000/api/v1/system/model
```

## Benchmark

```bash
python scripts/benchmark_quantization.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --modes fp16 int8 int4 \
  --repeats 3
```

The script records:

- mean generation latency;
- generated tokens per second;
- model memory footprint when available;
- peak allocated GPU memory when available;
- model load time;
- unsupported-mode/error information.

Results are written to `runtime/benchmarks/*.json` and `*.csv` and are intentionally ignored by Git. Keep the raw benchmark files when you need evidence for a resume/interview, and only quote values actually measured on your own hardware.

## Important interpretation

4-bit/8-bit quantization reduces model memory requirements, but lower precision does not guarantee lower end-to-end latency on every device. Always compare the same model, prompt, decoding settings and hardware before making a performance claim.

## Quality guardrail update

For the application path, quantized models no longer rewrite the deterministic report. They only generate a short auxiliary explanation. See `docs/QUALITY_EVALUATION_V2.md`.
