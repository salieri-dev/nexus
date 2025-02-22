import random
from typing import Dict, List, Optional


class TanksRepository:
    """Repository for managing tank data"""

    def __init__(self, db):
        self.db = db["nexus"]
        self.collection = self.db["tanks"]

    async def get_random_tank(self) -> Optional[Dict]:
        """Get a random tank from the collection."""
        pipeline = [{"$sample": {"size": 1}}]
        cursor = self.collection.aggregate(pipeline)
        tanks = await cursor.to_list(length=1)
        return tanks[0] if tanks else None

    async def get_tanks_by_tier(self, tier: int) -> List[Dict]:
        """Get all tanks of a specific tier."""
        cursor = self.collection.find({"tier": tier})
        return await cursor.to_list(length=None)

    async def search_tanks_by_name(self, name: str) -> List[Dict]:
        """Search tanks by name using case-insensitive regex."""
        regex = {"$regex": name, "$options": "i"}
        cursor = self.collection.find({
            "$or": [
                {"name": regex},
                {"short_name": regex}
            ]
        })
        return await cursor.to_list(length=None)

    async def upsert_tank(self, tank_data: Dict) -> str:
        """
        Insert or update a tank in the database.
        
        Args:
            tank_data: Dictionary containing tank information
        
        Returns:
            str: ID of the document
        """
        result = await self.collection.update_one(
            {"tank_id": tank_data["tank_id"]},  # Match by tank_id
            {"$set": tank_data},  # Update all fields
            upsert=True  # Create if doesn't exist
        )
        return tank_data["tank_id"]

    async def get_tank_by_id(self, tank_id: str) -> Optional[Dict]:
        """
        Get a tank by its ID.
        
        Args:
            tank_id: ID of the tank to retrieve
            
        Returns:
            Optional[Dict]: Tank document if found, None otherwise
        """
        return await self.collection.find_one({"_id": tank_id})

    async def get_all_tanks(self) -> List[Dict]:
        """
        Get all tanks from the database.
        
        Returns:
            List[Dict]: List of all tank documents
        """
        cursor = self.collection.find({})
        return await cursor.to_list(length=None)

    async def update_tank(self, tank_id: str, update_data: Dict) -> bool:
        """
        Update a tank document.
        
        Args:
            tank_id: ID of the tank to update
            update_data: Dictionary containing fields to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        result = await self.collection.update_one(
            {"_id": tank_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def delete_tank(self, tank_id: str) -> bool:
        """
        Delete a tank from the database.
        
        Args:
            tank_id: ID of the tank to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        result = await self.collection.delete_one({"_id": tank_id})
        return result.deleted_count > 0
