import os
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus
import structlog

# Get the shared logger instance
logger = structlog.get_logger()

class DatabaseClient:
    def __init__(self):
        self.username = quote_plus(os.getenv("MONGO_USERNAME", ""))
        self.password = quote_plus(os.getenv("MONGO_PASSWORD", ""))
        # Use service name in Docker, fallback to MONGO_BIND_IP
        self.host = os.getenv("MONGO_HOST", "mongodb") if os.getenv("DOCKER_ENV") else os.getenv("MONGO_BIND_IP", "localhost")
        self.port = os.getenv("MONGO_PORT", "27017")
        
        self.connection_string = (
            f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}"
            if self.username and self.password
            else f"mongodb://{self.host}:{self.port}"
        )
        
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None

    async def connect(self, database_name: str = "nexus"):
        """Connect to MongoDB and initialize the database."""
        try:
            logger.info("Connecting to MongoDB", host=self.host, port=self.port)
            self.client = AsyncIOMotorClient(self.connection_string)
            self.db = self.client[database_name]
            # Verify connection
            await self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB", host=self.host, port=self.port)
        except Exception as e:
            logger.error("Failed to connect to MongoDB", error=str(e), host=self.host, port=self.port)
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