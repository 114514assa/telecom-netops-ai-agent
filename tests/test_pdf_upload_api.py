"""No model, network, or real graph required; tests the actual FastAPI handler contract."""
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.core.auth import require_reader

PDF = (Path(__file__).parent / 'fixtures' / 'documented_interface_excerpt.pdf').read_bytes()


def client(monkeypatch):
    captured = {}

    class DummyGraph:
        def invoke(self, initial_state, config):
            captured['state'] = initial_state
            captured['config'] = config
            return {'status':'test_ok', 'raw_evidence':initial_state['raw_evidence']}

    class DummyAudit:
        def write(self, *args):
            pass

    monkeypatch.setattr(routes, 'runtime', SimpleNamespace(graph=DummyGraph(),audit=DummyAudit()))
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_reader] = lambda: None
    return TestClient(app), captured


def test_upload_pdf_extracts_text_only(monkeypatch):
    api, captured = client(monkeypatch)
    resp = api.post('/api/v1/documents/pdf/extract',files={'file':('sample.pdf',PDF,'application/pdf')})
    assert resp.status_code == 200
    assert 'GigabitEthernet0/0/15' in resp.json()['text']
    assert captured == {} # Extraction does not start any graph or enter RAG.


def test_upload_pdf_with_explicit_cli_type_starts_graph(monkeypatch):
    api, captured = client(monkeypatch)
    resp = api.post('/api/v1/incidents/from-pdf',
        data={'incident_json':json.dumps({'ip_address':'10.20.30.15','symptom':'sample VLAN check'}),
              'evidence_kind':'interface','observed_port':'GE0/0/15'},
        files={'file':('sample.pdf',PDF,'application/pdf')})
    assert resp.status_code == 200,resp.text
    evidence = captured['state']['raw_evidence']
    assert 'GigabitEthernet0/0/15' in evidence['interface_output']
    assert evidence['mac_output']==''
    assert evidence['source_system'].startswith('pdf_sha256:')
    assert evidence['collected_at'] is None # Parsing time is NOT device collection time.


def test_pdf_rejects_non_pdf(monkeypatch):
    api, _ = client(monkeypatch)
    resp = api.post('/api/v1/documents/pdf/extract',files={'file':('sample.pdf',b'not a pdf','application/pdf')})
    assert resp.status_code == 422
    assert resp.json()['detail']['code']=='invalid_pdf'
