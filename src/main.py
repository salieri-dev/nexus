import asyncio

from pyrogram import Client, idle

from src.database.client import DatabaseClient
from src.database.message_repository import MessageRepository, PeerRepository
from src.database.bot_config_repository import BotConfigRepository
from src.plugins.summary.job import init_summary
from src.plugins.summary import initialize as init_summary_config
from src.plugins.tanks import init_tanks
from src.plugins.threads import initialize as init_threads
from src.plugins.fanfic import initialize as init_fanfic
from src.utils.credentials import Credentials
from src.utils.logging import setup_structlog

# Setup logging once at the module level
logger = setup_structlog()


async def main():
    # Initialize credentials singleton and get shared database instance
    credentials = Credentials.get_instance()
    db = DatabaseClient.get_instance(credentials)

    try:
        # Initialize database connection
        await db.connect()

        # Initialize bot config repository
        config_repo = BotConfigRepository(db)
        await config_repo.initialize()

        # Initialize plugin configurations
        # Each plugin registers its own configuration
        await init_threads()
        await init_fanfic()
        await init_summary_config()

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
