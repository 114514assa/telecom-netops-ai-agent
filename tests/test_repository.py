from pathlib import Path

from app.data.repository import InventoryRepository


def test_repository_seed_and_query(tmp_path: Path):
    db = tmp_path / "inventory.sqlite3"
    repository = InventoryRepository(db)
    repository.initialize(Path("data/inventory.csv"))
    record = repository.find_by_ip("10.20.30.15")
    assert record is not None
    assert record.access_id == "ACC-SIM-003"
    assert record.expected_vlan == 200
