from typing import Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from src.utils.credentials import Credentials

# Get the shared logger instance
logger = structlog.get_logger()


class DatabaseClient:
    _instance = None
    _initialized = False

    def __new__(cls, credentials: Optional[Credentials] = None):
        if cls._instance is None:
            cls._instance = super(DatabaseClient, cls).__new__(cls)
            cls._instance.credentials = credentials or Credentials.from_env()
            cls._instance.connection_string = cls._instance.credentials.database.connection_string
            cls._instance.client: Optional[AsyncIOMotorClient] = None
            cls._instance.db = None
        return cls._instance

    async def connect(self, database_name: str = "nexus"):
        """Connect to MongoDB and initialize the database."""
        if not self._initialized:
            try:
                logger.info("Connecting to MongoDB",
                            host=self.credentials.database.host,
                            port=self.credentials.database.port)
                self.client = AsyncIOMotorClient(self.connection_string)
                self.db = self.client[database_name]
                # Verify connection
                await self.client.admin.command('ping')

                # Initialize rate limiting
                from src.database.ratelimit_repository import RateLimitRepository
                rate_limit_repo = RateLimitRepository(self)
                await rate_limit_repo.initialize()
                
                # Initialize bot configuration
                from src.database.bot_config_repository import BotConfigRepository
                bot_config_repo = BotConfigRepository(db_client=self)
                await bot_config_repo.initialize()

                self._initialized = True
                logger.info("Successfully connected to MongoDB",
                            host=self.credentials.database.host,
                            port=self.credentials.database.port)
            except Exception as e:
                logger.error("Failed to connect to MongoDB",
                             error=str(e),
                             host=self.credentials.database.host,
                             port=self.credentials.database.port)
                raise

    @classmethod
    def get_instance(cls, credentials: Optional[Credentials] = None) -> 'DatabaseClient':
        """Get the shared database client instance."""
        return cls(credentials)

    async def disconnect(self):
        """Close the MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")
