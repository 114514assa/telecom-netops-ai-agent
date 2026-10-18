from __future__ import annotations

from app.llm.backends import GenerationResult
from app.services.report import ReportComposer


def test_report_guardrail_sanitized_meta(monkeypatch):
    """No untrusted candidate text should be put in reports/checkpoints."""
    from app.core.config import Settings
    from app.domain.models import IncidentInput, EvidenceInput, DiagnosisResult
    from app.domain.enums import DiagnosisCode, Layer, Severity
    from app.parsers.aggregate import parse_all_evidence
    import app.services.report as module

    class FakeBackend:
        def generate_chat(self, messages):
            return GenerationResult(text="辅助说明：请重启交换机然后进行核查。", backend="test", model="fake")
    monkeypatch.setattr(module, "build_report_backend", lambda settings: FakeBackend())
    settings = Settings(llm_enabled=True, llm_backend="local_hf")
    composer = ReportComposer(settings)
    incident = IncidentInput(ip_address="10.20.30.15", symptom="演示故障")
    evidence = EvidenceInput()
    parsed = parse_all_evidence(evidence, target_mac=None, target_ip="10.20.30.15")
    diagnosis = DiagnosisResult(code=DiagnosisCode.VLAN_MISMATCH, likely_layer=Layer.L2, severity=Severity.HIGH,
                                confidence=0.9, summary="VLAN 与登记不一致", evidence=[], hypotheses=[], next_steps=[])
    report = composer.compose(incident, None, parsed, diagnosis, [])
    assert report.generated_by == "deterministic-template-fallback"
    assert "candidate_text" not in report.generation_meta["guardrail"]
    assert "请重启交换机" not in str(report.model_dump())
