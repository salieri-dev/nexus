from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
import structlog
from src.utils.credentials import Credentials

# Get the shared logger instance
logger = structlog.get_logger()

class DatabaseClient:
    def __init__(self, credentials: Optional[Credentials] = None):
        self.credentials = credentials or Credentials.from_env()
        self.connection_string = self.credentials.database.connection_string
        
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None

    async def connect(self, database_name: str = "nexus"):
        """Connect to MongoDB and initialize the database."""
        try:
            logger.info("Connecting to MongoDB",
                       host=self.credentials.database.host,
                       port=self.credentials.database.port)
            self.client = AsyncIOMotorClient(self.connection_string)
            self.db = self.client[database_name]
            # Verify connection
            await self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB",
                       host=self.credentials.database.host,
                       port=self.credentials.database.port)
        except Exception as e:
            logger.error("Failed to connect to MongoDB",
                        error=str(e),
                        host=self.credentials.database.host,
                        port=self.credentials.database.port)
            raise

    async def disconnect(self):
        """Close the MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

    async def insert_one(self, collection: str, document: Dict[str, Any]) -> str:
        """Insert a single document into a collection."""
        result = await self.db[collection].insert_one(document)
        return str(result.inserted_id)

    async def insert_many(self, collection: str, documents: List[Dict[str, Any]]) -> List[str]:
        """Insert multiple documents into a collection."""
        result = await self.db[collection].insert_many(documents)
        return [str(id) for id in result.inserted_ids]

    async def find_one(self, collection: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document matching the query."""
        return await self.db[collection].find_one(query)

    async def find_many(self, collection: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find all documents matching the query."""
        cursor = self.db[collection].find(query)
        return await cursor.to_list(length=None)

    async def update_one(self, collection: str, query: Dict[str, Any], update: Dict[str, Any]) -> int:
        """Update a single document matching the query."""
        result = await self.db[collection].update_one(query, {"$set": update})
        return result.modified_count

    async def update_many(self, collection: str, query: Dict[str, Any], update: Dict[str, Any]) -> int:
        """Update all documents matching the query."""
        result = await self.db[collection].update_many(query, {"$set": update})
        return result.modified_count

    async def delete_one(self, collection: str, query: Dict[str, Any]) -> int:
        """Delete a single document matching the query."""
        result = await self.db[collection].delete_one(query)
        return result.deleted_count

    async def delete_many(self, collection: str, query: Dict[str, Any]) -> int:
        """Delete all documents matching the query."""
        result = await self.db[collection].delete_many(query)
        return result.deleted_count

    async def count_documents(self, collection: str, query: Dict[str, Any]) -> int:
        """Count documents matching the query."""
        return await self.db[collection].count_documents(query)