import asyncio
from pyrogram import Client, idle
from src.utils.logging import setup_structlog
from src.database.client import DatabaseClient
from src.utils.credentials import Credentials

# Setup logging once at the module level
logger = setup_structlog()

async def main():
    # Load credentials
    credentials = Credentials.from_env()
    
    # Initialize and connect to database
    conn = DatabaseClient(credentials)
    try:
        await conn.connect()
        
        app = Client(
            credentials.bot.name,
            api_id=credentials.bot.app_id,
            api_hash=credentials.bot.app_hash,
            bot_token=credentials.bot.bot_token,
            plugins=dict(root="src/plugins"),
            mongodb=dict(connection=conn.client, remove_peers=False))
        
        logger.info("Starting Nexus")
        await app.start()
        await idle()
    except Exception as e:
        logger.error("Error in main loop", error=str(e))
        raise
    finally:
        logger.info("Shutting down Nexus")
        await conn.disconnect()
        if 'app' in locals():
            await app.stop()

if __name__ == "__main__":
    asyncio.run(main())