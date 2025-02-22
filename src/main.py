import asyncio
from pyrogram import Client, idle
import os
from src.utils.logging import setup_structlog
from src.database.client import DatabaseClient

# Setup logging once at the module level
logger = setup_structlog()

async def main():
    # Initialize and connect to database
    conn = DatabaseClient()
    try:
        await conn.connect()
        
        app = Client(
            "nexus",
            api_id=int(os.getenv("APP_ID")), 
            api_hash=os.getenv("APP_HASH"),  
            bot_token=os.getenv("BOT_TOKEN"),
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