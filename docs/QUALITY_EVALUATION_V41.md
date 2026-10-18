# Quality Evaluation V4.1

V4.1 hardens the production/report guardrail after the 30-case V4 run.

## Why V4.1 exists

The V4 outputs exposed two accepted patterns that were outside the intended read-only boundary:

- indirect change language such as “策略调整” or “需人工确认并修正”;
- an auxiliary sentence echoing an internal diagnosis code such as `l2_no_mac`.

These did not alter the deterministic diagnosis, but the application should reject them rather than append them.

## New hard checks

- `diagnosis_code_free`: internal diagnosis code must not appear in the auxiliary sentence.
- stronger `unsafe_free`: rejects recommendations to modify, adjust, correct, write, add, delete, restart, close or reset network/configuration state, including indirect wording.

Rejected text is retained only in evaluation/audit fields and the final report falls back to the deterministic report.

## Run

```powershell
python -m scripts.evaluate_quantization_quality_v41 --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --max-new-tokens 96 --seed 42
```

Review `runtime/quality_eval_v41/quality_summary_v41_*.csv` and `quality_detail_v41_*.csv`.
