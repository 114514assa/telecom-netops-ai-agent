from app.core.config import get_settings
from app.data.repository import InventoryRepository


if __name__ == "__main__":
    settings = get_settings()
    repository = InventoryRepository(settings.inventory_db)
    repository.initialize(settings.data_dir / "inventory.csv", force=True)
    print(f"Seeded inventory database: {settings.inventory_db}")
