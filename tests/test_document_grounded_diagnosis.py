"""Evaluate the five legacy synthetic scenarios, each linked to a source-doc fault pattern."""
import csv
import json
from pathlib import Path
from app.domain.models import IncidentInput, EvidenceInput, InventoryRecord
from app.parsers.aggregate import parse_all_evidence
from app.services.diagnosis import diagnose

ROOT=Path(__file__).parents[1]


def test_sourced_fault_patterns_preserve_original_outcomes():
    manifest=json.loads((ROOT/'data/evaluation/document_grounded_diagnosis_manifest.json').read_text('utf8'))
    rows=list(csv.DictReader((ROOT/'data/inventory.csv').open(encoding='utf8')))
    assets={r['ip_address']:InventoryRecord(**r) for r in rows}
    assert len(manifest)==5
    for case in manifest:
        assert case['source_page']>0 and case['source_section']
        assert case['sample_data_type'].startswith('existing_sanitized')
        payload=json.loads((ROOT/'data/sample_requests'/case['fixture']).read_text(encoding='utf8'))
        incident=IncidentInput.model_validate(payload['incident'])
        evidence=EvidenceInput.model_validate(payload['evidence'])
        inv=assets[incident.ip_address]
        parsed=parse_all_evidence(evidence,incident.target_mac,incident.ip_address,inv.registered_port)
        result=diagnose(incident,inv,parsed)
        assert result.code.value==case['expected_code'],(case['fixture'],result.code.value)
