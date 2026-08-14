import pytest

from app.core.config import Settings
from app.llm.backends import LocalHFBackend
from app.llm.factory import build_report_backend


def test_llm_disabled_keeps_template_backend(tmp_path):
    settings = Settings(
        llm_enabled=False,
        runtime_dir=tmp_path / "runtime",
        report_dir=tmp_path / "runtime/reports",
        checkpoint_db=tmp_path / "runtime/checkpoints.sqlite3",
        inventory_db=tmp_path / "runtime/inventory.sqlite3",
        audit_log=tmp_path / "runtime/audit.jsonl",
    )
    assert build_report_backend(settings) is None


def test_local_hf_config_builds_lazy_backend(tmp_path):
    settings = Settings(
        llm_enabled=True,
        llm_backend="local_hf",
        local_llm_model_id="demo/model",
        local_llm_quantization="int4",
        runtime_dir=tmp_path / "runtime",
        report_dir=tmp_path / "runtime/reports",
        checkpoint_db=tmp_path / "runtime/checkpoints.sqlite3",
        inventory_db=tmp_path / "runtime/inventory.sqlite3",
        audit_log=tmp_path / "runtime/audit.jsonl",
    )
    backend = build_report_backend(settings)
    assert isinstance(backend, LocalHFBackend)
    assert backend.quantization == "int4"
    assert backend.loaded is False


def test_local_hf_rejects_unknown_quantization():
    with pytest.raises(ValueError):
        LocalHFBackend(model_id="demo/model", quantization="int3")
