# Quantization Quality Evaluation V2

V2 fixes two issues found in the first evaluator:

1. Exact-string scoring could undercount correct facts after Markdown/punctuation changes.
2. A 0.5B model was allowed to rewrite the full deterministic diagnosis report, which let INT4 generation change the diagnosis itself.

## Production rule

The deterministic report is always preserved. The LLM may only return three constrained lines:

- `诊断代码：...` — exact copy
- `诊断结论：...` — exact copy
- `辅助说明：...` — short explanation based only on supplied evidence

The application rejects the LLM output and falls back to the deterministic report when any guardrail fails or local generation reaches the token limit.

## Smoke test

```powershell
python -m scripts.evaluate_quantization_quality --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --limit 3 --max-new-tokens 128
```

## Full evaluation

```powershell
python -m scripts.evaluate_quantization_quality --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --max-new-tokens 128
```

Outputs are written to `runtime/quality_eval_v2/`.

Primary automatic metric: `application_acceptance_rate`.

An output is accepted only when all of the following are true:

- diagnosis code is preserved exactly;
- deterministic conclusion is preserved exactly;
- the required three-line format is followed;
- no new IP/MAC/port/VLAN identifier is introduced;
- no production-changing operation is suggested;
- output is not truncated at `max_new_tokens`.

The manual review CSV remains necessary for semantic hallucinations that cannot be reliably captured by regular expressions.
