"""Strictly local, authorized-shaped, READ-ONLY simulated evidence collector.

This module never executes shell commands, SSH, SNMP or arbitrary URLs. The
fixtures are synthetic reproductions of document-described *types* of failures,
NOT original operator incidents or production CLI captures.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from app.domain.models import EvidenceInput, InventoryRecord

class CollectionUnavailable(RuntimeError):
    pass

class FixtureEvidenceCollector:
    def __init__(self, fixture_directory: Path):
        self.fixture_directory=Path(fixture_directory)

    def collect(self, inventory: InventoryRecord) -> EvidenceInput:
        # Fixed mapping of mock IPs -> supplied example files. No filesystem path from user input.
        known={
            '10.20.30.15':'vlan_mismatch.json',
            '10.132.10.22':'no_mac.json',
            '10.132.10.21':'interface_down.json',
            '10.20.30.17':'resource_mismatch.json',
            '10.20.30.16':'upstream.json',
        }
        filename=known.get(inventory.ip_address)
        if not filename:raise CollectionUnavailable('没有与资源记录对应的模拟只读采集样例')
        record=json.loads((self.fixture_directory/filename).read_text(encoding='utf-8'))
        if record['incident']['ip_address'] != inventory.ip_address:
            raise CollectionUnavailable('样例 IP 与资源记录不一致')
        # Observed device may deliberately differ in a resource conflict test.
        raw=record['evidence']
        return EvidenceInput.model_validate({**raw,'evidence_mode':'simulated_collection',
            'source_system':'fixture_readonly_collector','vendor':'sanitized_demo',
            'collected_at':datetime.now(timezone.utc)})
