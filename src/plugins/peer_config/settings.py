from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import Message
from structlog import get_logger
from typing import Dict, Any, List, Tuple

from src.database.client import DatabaseClient
from src.database.repository.peer_config_repository import PeerConfigRepository
from src.config.framework import (
    get_chat_setting as framework_get_setting,
    get_param_registry, get_param_info, update_chat_setting,
    PeerConfigModel
)

log = get_logger(__name__)


async def get_chat_setting(chat_id: int, setting_key: str, default=False) -> any:
    """Get a specific setting value for a chat.
    
    Args:
        chat_id: The chat ID to get peer_config for
        setting_key: The setting key to get (e.g. 'nsfw', 'transcribe', etc.)
        default: Default value if setting is not found (determines return type)
        
    Returns:
        The setting value with the same type as the default (bool or int)
    """
    try:
        # Use the framework function - it handles command name mapping internally
        return await framework_get_setting(chat_id, setting_key, default)
    except Exception as e:
        log.error("Error getting chat setting",
                  error=str(e),
                  chat_id=chat_id,
                  setting=setting_key)
        return default


def format_settings(config: dict) -> str:
    """Format peer_config for display in Russian."""
    # Remove chat_id and _id from display
    display_config = {k: v for k, v in config.items() if k not in ['chat_id', '_id']}

    # Format each setting
    settings_text = ["📋 Текущие настройки:"]

    # Get all registered parameters
    param_registry = get_param_registry()
    
    # Sort settings by type (core first, then by plugin)
    sorted_settings = sorted(
        display_config.items(),
        key=lambda item: (
            0 if param_registry.get(item[0], {}).param_type == "core" else 1,
            param_registry.get(item[0], {}).param_type if item[0] in param_registry else "zzz_unknown",
            item[0]
        )
    )

    # Display each setting with info from the registry
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
        "📝 Доступные настройки (используйте эти значения в командах):\n"
    ]
    
    # Get all registered parameters
    param_registry = get_param_registry()
    
    # Sort parameters by type
    sorted_params = sorted(
        param_registry.items(),
        key=lambda item: (
            0 if item[1].param_type == "core" else 1,
            item[1].param_type,
            item[0]
        )
    )
    
    # Add help text for each parameter
    for i, (param_name, param_info) in enumerate(sorted_params, 1):
        # Get command name from parameter info
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


@Client.on_message(filters.command(["config"]), group=1)
async def settings_handler(client: Client, message: Message):
    """Handle /config command."""
    try:
        # Check if private chat
        if message.chat.type == ChatType.PRIVATE:
            await message.reply_text(
                "❌ Настройки недоступны в личных сообщениях. В личных чатах NSFW и транскрибация всегда включены.")
            return

        # Initialize repository
        db_client = DatabaseClient.get_instance()
        config_repo = PeerConfigRepository(db_client.client)

        # Get current peer_config
        config = await config_repo.get_peer_config(message.chat.id)

        # If no additional arguments, display current peer_config and help
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

        # Direct value setting (like "/config dbai_submission_window 60")
        if action not in ['enable', 'disable']:
            # Get parameter info for the action (which is actually the setting name)
            param_name = PeerConfigModel.get_param_by_command(action)
            if not param_name:
                await message.reply_text(
                    "❌ Неверная настройка. Используйте /config для просмотра доступных настроек.")
                return
                
            param_info = get_param_info(param_name)
            if not param_info:
                await message.reply_text(
                    "❌ Неверная настройка. Используйте /config для просмотра доступных настроек.")
                return
                
            # Check if it's a non-boolean parameter
            if not isinstance(param_info.default, bool):
                try:
                    # Use our custom validation method
                    is_valid, new_value = PeerConfigModel.validate_param_value(param_name, setting)
                    if not is_valid:
                        await message.reply_text(f"❌ Неверное значение для {param_info.display_name}.")
                        return
                        
                    # Update the parameter
                    updated_config = await config_repo.update_peer_config(
                        message.chat.id,
                        {param_name: new_value}
                    )
                    
                    # Show success message
                    settings_text = format_settings(updated_config)
                    await message.reply_text(
                        f"✨ Настройки обновлены!\n\n{settings_text}"
                    )
                    
                    log.info(
                        "Updated peer_config for chat",
                        chat_id=message.chat.id,
                        setting=param_name,
                        value=new_value
                    )
                    return
                except (ValueError, IndexError):
                    await message.reply_text(f"❌ Неверное значение для {param_info.display_name}.")
                    return
            else:
                # It's a boolean but not using enable/disable syntax
                await message.reply_text(
                    f"❌ Настройка '{param_info.display_name}' является булевой. Используйте формат `/config enable {param_info.command_name}` или `/config disable {param_info.command_name}`."
                )
                return
        
        # Handle enable/disable for boolean settings
        if action not in ['enable', 'disable']:
            await message.reply_text(
                "❌ Неверное действие. Используйте 'enable', 'disable', или прямое значение для числовых настроек.")
            return
            
        # Get parameter info for the setting
        param_name = PeerConfigModel.get_param_by_command(setting)
        if not param_name:
            await message.reply_text(
                "❌ Неверная настройка. Используйте /config для просмотра доступных настроек.")
            return
            
        param_info = get_param_info(param_name)
        if not param_info:
            await message.reply_text(
                "❌ Неверная настройка. Используйте /config для просмотра доступных настроек.")
            return
            
        # Make sure it's a boolean setting
        if not isinstance(param_info.default, bool):
            await message.reply_text(
                f"❌ Настройка '{param_info.display_name}' не является булевой. Используйте формат `/config {param_info.command_name} значение`."
            )
            return

        # Update the boolean setting using our validation method
        is_valid, new_value = PeerConfigModel.validate_param_value(param_name, action == 'enable')
        if not is_valid:
            await message.reply_text(
                f"❌ Ошибка валидации для настройки '{param_info.display_name}'."
            )
            return
        
        # Update config
        updated_config = await config_repo.update_peer_config(
            message.chat.id,
            {param_name: new_value}
        )

        # Show updated peer_config
        settings_text = format_settings(updated_config)
        await message.reply_text(
            f"✨ Настройки обновлены!\n\n{settings_text}"
        )

        log.info(
            "Updated peer_config for chat",
            chat_id=message.chat.id,
            setting=param_name,
            value=new_value
        )

    except Exception as e:
        log.error("Error handling peer_config command", error=str(e))
        await message.reply_text("❌ Произошла ошибка при обновлении настроек.")
