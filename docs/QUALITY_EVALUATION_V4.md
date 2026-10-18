# Quantization Quality Evaluation V4

V4 is the final local-LLM quality evaluation protocol for the demo project.

## What changed from V3

1. The application Guardrail now checks diagnosis-aware semantic relevance, not only syntax/safety.
2. `access_side_normal` accepts normal-state wording such as “一致 / 未见异常 / 无需进一步核查 / 转交上层”, fixing the V3 false negative.
3. A rejected model sentence is retained as `candidate_text` in audit/evaluation output but is never appended to the report.
4. The final dataset contains 30 simulated/de-identified cases: 10 scenario families × 3 wording/data variants.
5. Evaluation metrics now match the real application decision. `application_acceptance_rate` means the same `validate_auxiliary_output()` decision used by `ReportComposer`.
6. V4 emits per-family metrics and rejection-reason counts.

## Final dataset

`data/evaluation/quality_cases_30.json`

Families:

- vlan_mismatch
- interface_down
- no_mac
- resource_port_mismatch
- upstream
- gateway_mismatch
- link_errors
- arp_missing
- device_mismatch
- normal_access

All records are simulated and are not production telecom data.

## Smoke test

Use the three cases that exercise the previous failure points:

```powershell
python -m scripts.evaluate_quantization_quality_v4 --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --case-ids vlan_mismatch_01 link_errors_01 normal_access_01 --max-new-tokens 96
```

## Final 30-case run

```powershell
python -m scripts.evaluate_quantization_quality_v4 --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --max-new-tokens 96 --seed 42
```

Output directory:

`runtime/quality_eval_v4/`

Important files:

- `quality_summary_v4_*.csv`: overall metrics by precision.
- `quality_family_v4_*.csv`: metrics by scenario family.
- `quality_detail_v4_*.csv`: case-level details and rejection reasons.
- `manual_review_v4_*.csv`: human review sheet.
- `quality_eval_v4_*.json`: full machine-readable record.

## Manual review

For each row, fill the five manual columns with `1` (pass) or `0` (fail):

- `manual_relevant`
- `manual_factual_safe`
- `manual_no_hallucination`
- `manual_action_boundary_ok`
- `manual_readable`

Then summarize:

```powershell
python -m scripts.summarize_manual_review_v4 runtime\quality_eval_v4\manual_review_v4_<timestamp>.csv
```

## Decision rule

Do not choose INT4 only because it uses less memory. Make the final deployment decision from both:

- fixed-length performance benchmark (`benchmark_quantization.py`), and
- V4 quality/safety evaluation.

A rejected LLM auxiliary note is a safe fallback, not a diagnostic failure: the deterministic report remains unchanged.
