"""HTTP contracts; run with the original agent dependencies installed."""
import csv
import io

import pytest

pytest.importorskip('langgraph')
pytest.importorskip('fastapi')

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.core.auth import require_reader


def build_client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_reader] = lambda: None
    return TestClient(app)


def test_testcase_catalog_and_json_response():
    client = build_client()
    response = client.get('/api/v1/testcases/document-grounded/categories')
    assert response.status_code == 200
    assert response.json()['total'] == 34
    response = client.get('/api/v1/testcases/document-grounded?category=vlan&limit=3')
    assert response.status_code == 200
    obj = response.json()
    assert obj['executed'] is False
    assert obj['count'] == 3
    assert all(c['verification_state'] == 'not_executed' for c in obj['cases'])


def test_csv_export_and_bad_input():
    client = build_client()
    response = client.get('/api/v1/testcases/document-grounded/export?format=csv&limit=2')
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 2
    assert rows[0]['test_id'] == 'RAG_DOC_001'
    assert client.get('/api/v1/testcases/document-grounded?category=not_a_source').status_code == 422
    assert client.get('/api/v1/testcases/document-grounded?limit=101').status_code == 422
