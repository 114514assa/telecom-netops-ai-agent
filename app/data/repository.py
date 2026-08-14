import csv
import sqlite3
from pathlib import Path

from app.domain.models import InventoryRecord


class InventoryRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self, csv_path: Path, force: bool = False) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory (
                    ip_address TEXT PRIMARY KEY,
                    access_id TEXT NOT NULL,
                    user_area TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    device_role TEXT NOT NULL,
                    device_location TEXT NOT NULL,
                    registered_port TEXT NOT NULL,
                    expected_vlan INTEGER NOT NULL,
                    network_domain TEXT NOT NULL,
                    expected_gateway TEXT,
                    expected_dns TEXT,
                    registered_mac TEXT
                )
                """
            )
            count = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
            if count and not force:
                return
            if force:
                conn.execute("DELETE FROM inventory")
            with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            conn.executemany(
                """
                INSERT OR REPLACE INTO inventory (
                    ip_address, access_id, user_area, device_name, device_role,
                    device_location, registered_port, expected_vlan, network_domain,
                    expected_gateway, expected_dns, registered_mac
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["ip_address"], row["access_id"], row["user_area"],
                        row["device_name"], row["device_role"], row["device_location"],
                        row["registered_port"], int(row["expected_vlan"]),
                        row["network_domain"], row.get("expected_gateway") or None,
                        row.get("expected_dns") or None, row.get("registered_mac") or None,
                    )
                    for row in rows
                ],
            )
            conn.commit()

    def find_by_ip(self, ip_address: str) -> InventoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE ip_address = ?", (ip_address,)
            ).fetchone()
        return InventoryRecord(**dict(row)) if row else None

    def list_all(self) -> list[InventoryRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM inventory ORDER BY ip_address").fetchall()
        return [InventoryRecord(**dict(row)) for row in rows]
