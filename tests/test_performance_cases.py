import json
from pathlib import Path

import pytest

from app.domain.models import StartIncidentRequest


CASE_NAMES = [
    "interface_down.json",
    "no_mac.json",
    "vlan_mismatch.json",
    "upstream.json",
    "resource_mismatch.json",
]


@pytest.mark.parametrize("name", CASE_NAMES)
def test_performance_sample_case_matches_real_api_schema(name: str):
    path = Path("data/sample_requests") / name
    assert path.exists(), f"missing sample case: {path}"
    payload = json.loads(path.read_text(encoding="utf-8"))
    validated = StartIncidentRequest.model_validate(payload)
    assert validated.incident.ip_address
    assert validated.incident.symptom
