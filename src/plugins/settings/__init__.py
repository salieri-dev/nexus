import structlog
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message
)
from pyrogram.enums import ChatMemberStatus, ChatType
from src.database.client import DatabaseClient
from src.plugins.settings.repository import PeerSettingsRepository

# Get the shared logger instance
logger = structlog.get_logger()

# Initialize repository
db_client = DatabaseClient.get_instance()
settings_repo = PeerSettingsRepository(db_client.client)

def get_settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Generate settings keyboard markup."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "NSFW",
                callback_data=f"toggle_nsfw:{chat_id}"
            )
        ]
    ])

async def can_change_settings(client: Client, chat_id: int, user_id: int) -> bool:
    """Check if user can change chat settings."""
    try:
        # User must be an admin or owner
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception as e:
        logger.error("Error checking user permissions",
                    error=str(e),
                    chat_id=chat_id,
                    user_id=user_id)
        return False

@Client.on_message(filters.command("settings"), group=1)
async def settings_command(client: Client, message: Message):
    """Handle /settings command."""
    try:
        # Settings are only available in groups
        if message.chat.type == ChatType.PRIVATE:
            await message.reply("⚠️ Настройки доступны только в группах")
            return

        # Check if user can change settings
        if not await can_change_settings(client, message.chat.id, message.from_user.id):
            await message.reply("❌ У вас нет прав для изменения настроек")
            return

        # Get current settings
        settings = await settings_repo.get_peer_settings(message.chat.id)
        nsfw_status = "✅ Разрешено" if settings and settings.get("nsfw_allowed") else "❌ Запрещено"
        
        await message.reply(
            f"⚙️ Настройки\n\nNSFW контент: {nsfw_status}",
            reply_markup=get_settings_keyboard(message.chat.id)
        )
    except Exception as e:
        logger.error("Error handling settings command",
                    error=str(e),
                    chat_id=message.chat.id)
        await message.reply("❌ Произошла ошибка при загрузке настроек")

@Client.on_callback_query(filters.regex(r"^toggle_nsfw:(-?\d+)$"), group=1)
async def handle_nsfw_toggle(client: Client, callback_query: CallbackQuery):
    """Handle NSFW toggle button press."""
    try:
        chat_id = int(callback_query.matches[0].group(1))
        
        # Verify user has permission to change settings
        if not await can_change_settings(client, chat_id, callback_query.from_user.id):
            await callback_query.answer(
                "❌ У вас нет прав для изменения настроек",
                show_alert=True
            )
            return

        # Get current settings and toggle NSFW
        current_settings = await settings_repo.get_peer_settings(chat_id)
        current_nsfw = current_settings.get("nsfw_allowed", False) if current_settings else False
        new_nsfw = not current_nsfw
        
        # Update settings
        if await settings_repo.toggle_nsfw(chat_id, new_nsfw):
            nsfw_status = "✅ Разрешено" if new_nsfw else "❌ Запрещено"
            await callback_query.message.edit_text(
                f"⚙️ Настройки\n\nNSFW контент: {nsfw_status}",
                reply_markup=get_settings_keyboard(chat_id)
            )
            await callback_query.answer(
                "✅ Настройки обновлены",
                show_alert=False
            )
        else:
            await callback_query.answer(
                "❌ Ошибка при обновлении настроек",
                show_alert=False
            )
    except Exception as e:
        logger.error("Error handling NSFW toggle",
                    error=str(e),
                    callback_data=callback_query.data)
        await callback_query.answer(
            "❌ Произошла ошибка",
            show_alert=False
        )