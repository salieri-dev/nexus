from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType
from structlog import get_logger

from src.database.message_repository import PeerRepository
from src.database.client import DatabaseClient

log = get_logger(__name__)

async def get_chat_setting(chat_id: int, setting_key: str, default: bool = False) -> bool:
    """Get a specific setting value for a chat.
    
    Args:
        chat_id: The chat ID to get settings for
        setting_key: The setting key to get (e.g. 'nsfw', 'transcribe', etc.)
        default: Default value if setting is not found
        
    Returns:
        bool: The setting value
    """
    try:
        # Initialize repository
        db_client = DatabaseClient.get_instance()
        peer_repo = PeerRepository(db_client.client)
        
        # Get current settings
        config = await peer_repo.get_peer_config(chat_id)
        
        # Map user-friendly names to config keys
        setting_map = {
            'nsfw': 'nsfw_enabled',
            'transcribe': 'transcribe_enabled',
            'summary': 'summary_enabled',
            'nhentai_blur': 'nhentai_blur'
        }
        
        # Get the actual config key
        config_key = setting_map.get(setting_key, setting_key)
        
        return config.get(config_key, default)
        
    except Exception as e:
        log.error("Error getting chat setting",
                 error=str(e),
                 chat_id=chat_id,
                 setting=setting_key)
        return default

def format_settings(config: dict) -> str:
    """Format settings for display in Russian."""
    # Remove chat_id and _id from display
    display_config = {k: v for k, v in config.items() if k not in ['chat_id', '_id']}
    
    # Format each setting
    settings_text = ["📋 Текущие настройки:"]
    
    # Translation mapping with emojis
    translations = {
        'nsfw_enabled': ('🔞 NSFW', 'Фильтрация NSFW контента'),
        'transcribe_enabled': ('🎙 Транскрибация', 'Преобразование голосовых сообщений в текст'),
        'summary_enabled': ('📝 Суммаризация', 'Создание кратких обзоров длинных текстов'),
        'nhentai_blur': ('🌫 NHentai blur', 'Размытие превью изображений')
    }
    
    for key, value in display_config.items():
        # Get translated name and description
        setting_name, _ = translations.get(key, (key, ''))
        # Convert boolean to enabled/disabled in Russian with emojis
        status = "✅ включено" if value else "❌ выключено"
        settings_text.append(f"{setting_name}: {status}")
    
    return "\n".join(settings_text)

def get_help_text() -> str:
    """Get detailed help text about settings."""
    return (
        "ℹ️ Помощь по настройкам:\n\n"
        "🔹 Основные команды:\n"
        "• /settings - Показать текущие настройки\n"
        "• /settings enable <настройка> - Включить настройку\n"
        "• /settings disable <настройка> - Выключить настройку\n\n"
        "📝 Доступные настройки (используйте эти значения в командах):\n\n"
        "1️⃣ nsfw\n"
        "   🔸 Фильтрация NSFW контента\n"
        "   🔸 Пример: `/settings enable nsfw`\n\n"
        "2️⃣ transcribe\n"
        "   🔸 Преобразование голосовых сообщений в текст\n"
        "   🔸 Пример: `/settings disable transcribe`\n\n"
        "3️⃣ summary\n"
        "   🔸 Создание саммари чата каждый день\n"
        "   🔸 Пример: `/settings enable summary`\n\n"
        "4️⃣ nhentai_blur\n"
        "   🔸 Размытие превью изображений в /nhentai\n"
        "   🔸 Пример: `/settings disable nhentai_blur`"
    )

@Client.on_message(filters.command(["settings", "config"]), group=1)
async def settings_handler(client: Client, message: Message):
    """Handle /settings command."""
    try:
        # Check if private chat
        if message.chat.type == ChatType.PRIVATE:
            await message.reply_text("❌ Настройки недоступны в личных сообщениях. В личных чатах NSFW и транскрибация всегда включены.")
            return

        # Initialize repository
        db_client = DatabaseClient.get_instance()
        peer_repo = PeerRepository(db_client.client)
        
        # Get current settings
        config = await peer_repo.get_peer_config(message.chat.id)
        
        # If no additional arguments, display current settings and help
        if len(message.command) == 1:
            settings_text = format_settings(config)
            help_text = get_help_text()
            await message.reply_text(f"{settings_text}\n\n{help_text}")
            return

        # Handle enable/disable commands
        if len(message.command) < 3:
            await message.reply_text(get_help_text())
            return

        action = message.command[1].lower()
        setting = message.command[2].lower()

        # Map user-friendly names to config keys
        setting_map = {
            'nsfw': 'nsfw_enabled',
            'transcribe': 'transcribe_enabled',
            'summary': 'summary_enabled',
            'nhentai_blur': 'nhentai_blur'
        }

        if action not in ['enable', 'disable']:
            await message.reply_text("❌ Неверное действие. Используйте 'enable' или 'disable'.")
            return

        if setting not in setting_map:
            await message.reply_text(
                "❌ Неверная настройка. Используйте /settings для просмотра доступных настроек."
            )
            return

        # Update the setting
        setting_key = setting_map[setting]
        new_value = action == 'enable'
        
        # Update config
        updated_config = await peer_repo.update_peer_config(
            message.chat.id,
            {setting_key: new_value}
        )

        # Show updated settings
        settings_text = format_settings(updated_config)
        await message.reply_text(
            f"✨ Настройки обновлены!\n\n{settings_text}"
        )

        log.info(
            f"Updated settings for chat",
            chat_id=message.chat.id,
            setting=setting_key,
            value=new_value
        )

    except Exception as e:
        log.error("Error handling settings command", error=str(e))
        await message.reply_text("❌ Произошла ошибка при обновлении настроек.")