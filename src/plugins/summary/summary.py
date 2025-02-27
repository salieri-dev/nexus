"""Summary command handlers for chat summarization"""

from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import Message
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.message_repository import MessageRepository
from src.database.repository.peer_config_repository import PeerConfigRepository
from src.plugins.help import command_handler
from src.security.rate_limiter import rate_limit
from src.utils.helpers import is_private_chat, is_developer
from .job import init_summary, MOSCOW_TZ, InsufficientDataError

log = get_logger(__name__)


def get_message_repository():
    """Get message repository instance"""
    db_client = DatabaseClient.get_instance()
    return MessageRepository(db_client.client)


def get_peer_config_repository():
    """Get peer config repository instance"""
    db_client = DatabaseClient.get_instance()
    return PeerConfigRepository(db_client.client)


@command_handler(
    commands=["summarize_yesterday"],
    description="Генерирует сводку чата за вчерашний день",
    group="Аналитика"
)
@Client.on_message(filters.command(["summarize_yesterday"]), group=1)
@rate_limit(
    operation="summarize_yesterday_handler",
    window_seconds=10,
    on_rate_limited=lambda message: message.reply("🕒 Подождите 1 минуту перед следующим запросом!")
)
async def summarize_yesterday_handler(client: Client, message: Message):
    """Handle /summarize_yesterday command to generate a summary for yesterday"""
    # Only allow in groups/supergroups
    if is_private_chat(message):
        await message.reply_text(
            text="❌ Эта команда доступна только в групповых чатах.",
            quote=True
        )
        return

    if not is_developer(message.from_user.id):
        await message.reply_text(
            text="❌ Эта команда доступна только для разработчиков.",
            quote=True
        )
        return

    # Check if summarization is enabled for this chat
    from src.config.framework import get_chat_setting
    if not await get_chat_setting(message.chat.id, "summary_enabled", default=False):
        await message.reply_text(
            text="❌ Функция суммаризации не включена для этого чата. Используйте /summary для включения.",
            quote=True
        )
        return

    # Get yesterday's date in Moscow timezone
    yesterday = datetime.now(MOSCOW_TZ) - timedelta(days=1)
    
    await generate_summary_for_date(client, message, yesterday, "вчерашний день")


@command_handler(
    commands=["summarize_today"],
    description="Генерирует сводку чата за сегодняшний день",
    group="Аналитика"
)
@Client.on_message(filters.command(["summarize_today"]), group=1)
@rate_limit(
    operation="summarize_today_handler",
    window_seconds=60,
    on_rate_limited=lambda message: message.reply("🕒 Подождите 1 минуту перед следующим запросом!")
)
async def summarize_today_handler(client: Client, message: Message):
    """Handle /summarize_today command to generate a summary for today"""
    # Only allow in groups/supergroups
    if is_private_chat(message):
        await message.reply_text(
            text="❌ Эта команда доступна только в групповых чатах.",
            quote=True
        )
        return

    if not is_developer(message.from_user.id):
        await message.reply_text(
            text="❌ Эта команда доступна только для разработчиков.",
            quote=True
        )
        return
    # Check if summarization is enabled for this chat
    from src.config.framework import get_chat_setting
    if not await get_chat_setting(message.chat.id, "summary_enabled", default=False):
        await message.reply_text(
            text="❌ Функция суммаризации не включена для этого чата. Используйте /summary для включения.",
            quote=True
        )
        return

    # Get today's date in Moscow timezone
    today = datetime.now(MOSCOW_TZ)
    
    await generate_summary_for_date(client, message, today, "сегодняшний день")


async def generate_summary_for_date(client: Client, message: Message, date: datetime, date_description: str):
    """Generate and send a summary for the specified date
    
    Args:
        client: The Pyrogram client
        message: The message that triggered the command
        date: The date to generate the summary for
        date_description: Human-readable description of the date (e.g., "вчерашний день")
    """
    # Send initial message
    init_msg = await message.reply_text(
        text=f"🔍 Анализирую сообщения за {date_description}...",
        quote=True
    )
    
    try:
        # Get repositories
        message_repository = get_message_repository()
        peer_config_repository = get_peer_config_repository()
        
        # Initialize the summary job
        summary_job = await init_summary(message_repository, peer_config_repository, client)
        
        # Generate the summary
        chat_title = message.chat.title or str(message.chat.id)
        summary_text = await summary_job.generate_chat_summary(
            chat_id=message.chat.id,
            chat_title=chat_title,
            date=date,
            is_forced=True  # Force generation even if there are few messages
        )
        
        if summary_text:
            # Delete the initial message
            await init_msg.delete()
            
            # Send the summary
            await message.reply_text(
                text=summary_text,
                quote=True,
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await init_msg.edit_text(
                f"❌ Не удалось сгенерировать сводку за {date_description}. Возможно, недостаточно сообщений."
            )
            
    except InsufficientDataError as e:
        log.info(f"Insufficient data for summary: {e}")
        await init_msg.edit_text(
            f"📊 Недостаточно сообщений для генерации сводки за {date_description}. "
            f"Необходимо минимум 60 сообщений."
        )
    except Exception as e:
        log.error(f"Error generating summary: {e}")
        await init_msg.edit_text(
            f"❌ Произошла ошибка при генерации сводки: {str(e)}"
        )