import asyncio
from pyrogram import Client, idle
from src.utils.logging import setup_structlog
from src.database.client import DatabaseClient
from src.utils.credentials import Credentials
from src.plugins.tanks import init_tanks
from src.database.message_repository import MessageRepository, PeerRepository
from src.plugins.summary.job import init_summary

# Setup logging once at the module level
logger = setup_structlog()


async def main():
    # Initialize credentials singleton and get shared database instance
    credentials = Credentials.get_instance()
    db = DatabaseClient.get_instance(credentials)

    try:
        # Initialize database connection
        await db.connect()

        # Initialize tanks data
        await init_tanks()

        # Initialize client
        app = Client(
            credentials.bot.name,
            api_id=credentials.bot.app_id,
            api_hash=credentials.bot.app_hash,
            bot_token=credentials.bot.bot_token,
            plugins=dict(root="src/plugins"),
            mongodb=dict(connection=db.client, remove_peers=False))

        logger.info("Starting Nexus")
        await app.start()
        
        # Initialize repositories and summary job after app is started
        message_repository = MessageRepository(db.client)
        peer_repository = PeerRepository(db.client)
        await init_summary(message_repository, peer_repository, app)
        
        await idle()
    except Exception as e:
        logger.error("Error in main loop", error=str(e))
        raise
    finally:
        logger.info("Shutting down Nexus")
        await db.disconnect()
        if 'app' in locals():
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
