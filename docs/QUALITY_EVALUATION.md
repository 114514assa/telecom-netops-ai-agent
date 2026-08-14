# Local LLM quality evaluation

This project evaluates quantization in two separate dimensions:

1. **Efficiency**: latency, tokens/s, model memory, peak GPU memory (`benchmark_quantization.py`).
2. **Quality**: fact retention, diagnosis-code consistency, key-report coverage, unexpected network identifiers, unsafe configuration instructions (`evaluate_quantization_quality.py`).

Automatic quality checks are deliberately conservative. Semantic hallucinations and readability must still be manually reviewed in the generated `manual_review_*.csv`.

## Smoke test

```powershell
python -m scripts.evaluate_quantization_quality --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --limit 3 --max-new-tokens 384
```

## Formal comparison

```powershell
python -m scripts.evaluate_quantization_quality --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --max-new-tokens 384
```

INT8 can be added, but on some consumer GPUs it may be much slower and is not required if the deployment choice is between FP16 and INT4.

## Outputs

Saved under `runtime/quality_eval/`:

- `quality_summary_*.csv`: mode-level aggregate results.
- `quality_detail_*.csv`: per-case automatic checks and outputs.
- `manual_review_*.csv`: manual review worksheet.
- `quality_eval_*.json`: full machine-readable result.

## Manual review fields

Fill with `1` for pass/yes and `0` for fail/no:

- `manual_factual_correct`: all key facts are accurate.
- `manual_diagnosis_correct`: generated conclusion matches deterministic diagnosis.
- `manual_hallucination`: 1 means hallucination exists; 0 means none found.
- `manual_format_acceptable`: report is readable and preserves expected structure.

For a resume or report, only claim quality retention after completing this manual review on the stated number of simulated cases.
