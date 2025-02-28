# src/plugins/peer_config/settings.py
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ChatMemberStatus
from pyrogram.types import Message
from structlog import get_logger
from typing import Dict, Any, List, Tuple, Optional

from src.database.client import DatabaseClient
from src.database.repository.peer_config_repository import PeerConfigRepository
from src.config.framework import get_chat_setting as framework_get_setting, get_param_registry, get_param_info, update_chat_setting, PeerConfigModel
from src.plugins.help import command_handler

log = get_logger(__name__)


async def get_chat_setting(chat_id: int, setting_key: str, default=False) -> any:
    """
    Get a specific setting value for a chat.

    This is a pass-through to the framework function for backward compatibility.

    Args:
        chat_id: The chat ID to get peer_config for
        setting_key: The setting key to get (e.g. 'nsfw', 'transcribe', etc.)
        default: Default value if setting is not found (determines return type)

    Returns:
        The setting value with the same type as the default (bool or int)
    """
    try:
        return await framework_get_setting(chat_id, setting_key, default)
    except Exception as e:
        log.error("Error getting chat setting", error=str(e), chat_id=chat_id, setting=setting_key)
        return default


def format_settings(config: dict) -> str:
    """Format peer_config for display in Russian."""
    # Remove chat_id and _id from display
    display_config = {k: v for k, v in config.items() if k not in ["chat_id", "_id"]}

    # Get all registered parameters
    param_registry = get_param_registry()

    # Sort settings by type (core first, then by plugin)
    sorted_settings = sorted(display_config.items(), key=lambda item: (0 if param_registry.get(item[0], {}).param_type == "core" else 1, param_registry.get(item[0], {}).param_type if item[0] in param_registry else "zzz_unknown", item[0]))

    # Format each setting with info from the registry
    settings_text = ["📋 Текущие настройки:"]
    for key, value in sorted_settings:
        # Skip if not in registry (might be legacy or internal)
        if key not in param_registry:
            continue

        param_info = param_registry[key]
        setting_name = param_info.display_name

        # Add emoji based on parameter type
        param_type = param_info.param_type
        if param_type == "core":
            setting_name = f"🔷 {setting_name}"
        else:
            plugin_name = param_type.split(":", 1)[1] if ":" in param_type else "plugin"
            setting_name = f"🔶 {setting_name} ({plugin_name})"

        # Format value based on type
        value_type = type(param_info.default)
        if value_type == bool:
            status = "✅ включено" if value else "❌ выключено"
        elif value_type == int:
            status = f"🔢 {value}"
        else:
            status = str(value)

        settings_text.append(f"{setting_name}: {status}")

    return "\n".join(settings_text)


def get_help_text() -> str:
    """Get detailed help text about peer_config."""
    # Base help text
    help_text = [
        "ℹ️ Помощь по настройкам:\n",
        "🔹 Основные команды:",
        "• /config - Показать текущие настройки",
        "• /config enable <настройка> - Включить настройку (для булевых значений)",
        "• /config disable <настройка> - Выключить настройку (для булевых значений)",
        "• /config <настройка> <значение> - Установить числовое значение\n",
        "📝 Доступные настройки (используйте эти значения в командах):\n",
    ]

    # Get all registered parameters and sort them
    param_registry = get_param_registry()
    sorted_params = sorted(param_registry.items(), key=lambda item: (0 if item[1].param_type == "core" else 1, item[1].param_type, item[0]))

    # Add help text for each parameter
    for i, (param_name, param_info) in enumerate(sorted_params, 1):
        command = param_info.command_name

        # Get plugin info if applicable
        plugin_text = ""
        if param_info.param_type != "core":
            plugin_name = param_info.param_type.split(":", 1)[1] if ":" in param_info.param_type else "plugin"
            plugin_text = f"[{plugin_name}] "

        help_text.append(f"{i}️⃣ {command}")
        help_text.append(f"   🔸 {plugin_text}{param_info.description}")

        # Add example based on type
        if isinstance(param_info.default, bool):
            help_text.append(f"   🔸 Пример: `/config enable {command}`\n")
        else:
            help_text.append(f"   🔸 Пример: `/config {command} {param_info.default}`\n")

    return "\n".join(help_text)


async def is_user_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Check if user is an admin in the chat."""
    try:
        chat_member = await client.get_chat_member(chat_id=chat_id, user_id=user_id)
        allowed_statuses = [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        return chat_member.status in allowed_statuses
    except Exception as e:
        log.error("Error checking admin status", error=str(e))
        return False


async def handle_show_settings(chat_id: int) -> str:
    """Handle request to show current settings."""
    try:
        # Initialize repository
        db_client = DatabaseClient.get_instance()
        config_repo = PeerConfigRepository(db_client.client)

        # Get current peer_config and format it
        config = await config_repo.get_peer_config(chat_id)
        settings_text = format_settings(config)
        help_text = get_help_text()
        return f"{settings_text}\n\n{help_text}"
    except Exception as e:
        log.error("Error showing settings", error=str(e), chat_id=chat_id)
        return "❌ Произошла ошибка при получении настроек."


async def handle_setting_change(chat_id: int, action: str, setting: str) -> str:
    """Handle changing a setting value."""
    try:
        # Get parameter info
        param_name = PeerConfigModel.get_param_by_command(action)

        # If action isn't a setting name, it might be enable/disable
        if not param_name and action in ["enable", "disable"]:
            param_name = PeerConfigModel.get_param_by_command(setting)
            is_bool_command = True
        else:
            is_bool_command = False

        # Check if setting exists
        if not param_name:
            return "❌ Неверная настройка. Используйте /config для просмотра доступных настроек."

        # Get parameter info
        param_info = get_param_info(param_name)
        if not param_info:
            return "❌ Неверная настройка. Используйте /config для просмотра доступных настроек."

        # Handle boolean settings (enable/disable)
        if is_bool_command:
            if not isinstance(param_info.default, bool):
                return f"❌ Настройка '{param_info.display_name}' не является булевой. Используйте формат `/config {param_info.command_name} значение`."

            new_value = action == "enable"

        # Handle non-boolean settings
        else:
            if isinstance(param_info.default, bool):
                return f"❌ Настройка '{param_info.display_name}' является булевой. Используйте формат `/config enable {param_info.command_name}` или `/config disable {param_info.command_name}`."

            # Validate and convert the value
            is_valid, new_value = PeerConfigModel.validate_param_value(param_name, setting)
            if not is_valid:
                return f"❌ Неверное значение для {param_info.display_name}."

        # Update the config
        updated_config = await update_chat_setting(chat_id, param_name, new_value)

        # Format the response
        settings_text = format_settings(updated_config)

        log.info("Updated peer_config for chat", chat_id=chat_id, setting=param_name, value=new_value)

        return f"✨ Настройки обновлены!\n\n{settings_text}"

    except Exception as e:
        log.error("Error handling setting change", error=str(e), chat_id=chat_id)
        return "❌ Произошла ошибка при обновлении настроек."


@Client.on_message(filters.command(["config"]), group=1)
@command_handler(commands=["config"], description="Изменить настройки чата (здесь можно включить NSFW, настроить параметры игр)", group="Утилиты")
async def settings_handler(client: Client, message: Message):
    """Handle /config command to manage chat settings."""
    try:
        # Check if private chat
        if message.chat.type == ChatType.PRIVATE:
            await message.reply_text("❌ Настройки недоступны в личных сообщениях. В личных чатах NSFW и транскрибация всегда включены.")
            return

        # If no additional arguments, just display current settings and help
        if len(message.command) == 1:
            response_text = await handle_show_settings(message.chat.id)
            await message.reply_text(response_text)
            return

        # For changing settings, check if user is admin or owner
        if not await is_user_admin(client, message.chat.id, message.from_user.id):
            await message.reply_text("❌ Только администраторы чата могут изменять настройки.")
            return

        # Handle setting changes
        if len(message.command) < 3:
            await message.reply_text(get_help_text())
            return

        action = message.command[1].lower()
        setting = message.command[2].lower()

        response = await handle_setting_change(message.chat.id, action, setting)
        await message.reply_text(response)

    except Exception as e:
        log.error("Error handling config command", error=str(e))
        await message.reply_text("❌ Произошла ошибка при обработке команды настроек.")
