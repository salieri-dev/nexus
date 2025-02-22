import httpx
from typing import Dict, List
from structlog import get_logger
import json
from src.plugins.tanks.repository import TanksRepository

# Get the shared logger instance
log = get_logger(__name__)

API_URL = "https://tanks.gg/api/v13200ru/list"
TANK_IMAGE_URL = "https://assets.tanks.gg/icons/ru-tanks/standard/{country}-{tank_id}.png"


class TankService:
    def __init__(self, repository: TanksRepository):
        self.repository = repository
        self.http_client = httpx.AsyncClient()

    async def fetch_tanks(self) -> List[Dict]:
        """Fetch tanks data from the API."""
        try:
            response = await self.http_client.get(API_URL)
            response.raise_for_status()
            data = response.json()
            return data.get("tanks", [])
        except httpx.HTTPError as e:
            log.error("Failed to fetch tanks data", error=str(e))
            raise

    def format_tank_data(self, tank: Dict) -> Dict:
        """Format tank data and add image URL."""
        # Parse regions from JSON string
        try:
            regions = json.loads(tank.get("regions_json", "[]"))
        except json.JSONDecodeError:
            regions = []

        return {
            "tank_id": tank["id"],
            "name": tank["name"],
            "short_name": tank.get("short_name"),
            "slug": tank.get("slug"),
            "type": tank.get("type"),
            "tier": tank.get("tier", 0),
            "price": tank.get("price", 0),
            "gold_price": tank.get("gold_price", 0),
            "not_in_shop": tank.get("not_in_shop", False),
            "nation": tank.get("nation"),
            "tags": tank.get("tags", "").split(","),
            "regions": regions,
            "original_id": tank.get("original_id"),
            "image_url": TANK_IMAGE_URL.format(
                country=tank.get("nation", "unknown").lower(),
                tank_id=tank["id"]
            )
        }

    async def clear_tanks(self):
        """Clear all tanks from the database."""
        try:
            await self.repository.collection.delete_many({})
            log.info("Cleared all tanks from database")
        except Exception as e:
            log.error("Failed to clear tanks", error=str(e))
            raise

    async def sync_tanks(self, clear_existing: bool = True) -> int:
        """
        Fetch tanks from API and sync to database.
        
        Args:
            clear_existing: If True, clear all existing tanks before syncing
        
        Returns:
            int: Number of tanks synced
        """
        try:
            # Optionally clear existing tanks
            if clear_existing:
                await self.clear_tanks()

            # Fetch tanks from API
            tanks_data = await self.fetch_tanks()

            # Format tank data
            formatted_tanks = [
                self.format_tank_data(tank)
                for tank in tanks_data
            ]

            # Save each tank to repository
            count = 0
            for tank in formatted_tanks:
                try:
                    await self.repository.upsert_tank(tank)
                    count += 1
                except Exception as e:
                    log.error(
                        "Failed to save tank",
                        tank_id=tank["tank_id"],
                        error=str(e)
                    )

            log.info(f"Successfully synced {count} tanks")
            return count

        except Exception as e:
            log.error("Failed to sync tanks", error=str(e))
            raise
        finally:
            await self.http_client.aclose()
