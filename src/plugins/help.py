"""Dynamic help command handler"""
from typing import Dict, List
from functools import wraps
from pyrogram import Client, filters
from pyrogram.types import Message
from structlog import get_logger

log = get_logger(__name__)

# Store for command help information
command_help: Dict[str, Dict] = {}


def command_handler(commands: List[str], description: str, example: str = None, group: str = "Общие"):
    """Decorator to register command help information.
    
    Args:
        commands: List of command names (without /)
        description: Command description
        example: Optional example usage
        group: Command group for organization
    """

    def decorator(func):
        # Register help info for each command
        for cmd in commands:
            command_help[cmd] = {
                'description': description,
                'example': example,
                'group': group
            }

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


@Client.on_message(filters.command("help"))
async def help_handler(client: Client, message: Message):
    """Dynamic help command that shows available commands grouped by category"""
    try:
        # Group commands by handler (using description as key)
        handlers: Dict[str, Dict] = {}

        for cmd, info in command_help.items():
            key = f"{info['group']}:{info['description']}"
            if key not in handlers:
                handlers[key] = {
                    'commands': [],
                    'description': info['description'],
                    'example': info['example'],
                    'group': info['group']
                }
            handlers[key]['commands'].append(cmd)

        # Define emoji mapping for groups
        group_emojis = {
            'Утилиты': '📎',
            'Игры': '🎮',
            'NSFW': '🔞',
            'Мемы': '🤪',
            'Изображения': '🖼️',
            'Сообщения': '✍️',
            'Рандом': '🎲'
        }

        # Group handlers by category
        groups: Dict[str, List[Dict]] = {}
        for handler in handlers.values():
            group = handler['group']
            if group not in groups:
                groups[group] = []

            # Sort commands for consistent output
            handler['commands'].sort()
            groups[group].append(handler)

        # Build help message
        help_text = []

        # Add command sections
        for group, handlers in sorted(groups.items()):
            emoji = group_emojis.get(group, '🔹')
            help_text.append(f"\n{emoji} {group}:")

            for handler in sorted(handlers, key=lambda x: x['commands'][0]):
                commands = ', '.join(f"/{cmd}" for cmd in handler['commands'])
                # Add NSFW emoji if in NSFW group
                nsfw_mark = " 🔞" if group == "NSFW" else ""
                help_text.append(f"• {commands} — {handler['description']}{nsfw_mark}")

        # Add passive functionality section in blockquote
        help_text.extend([
            "\n**Пассивный функционал:**",
            "• Скачивает рилзы из Instagram",
            "• Переводит войсы в текст",
            ">Вы можете включить суммаризацию чата, отключить расшифровку голосовых и многое другое в чатах через команду /settings! "
            "\n>Команды отмеченные 🔞 могут быть использованы в групповых чатах только если в настройках разрешен соответствующий контент. "
            "Бот находится в стадии бета-тестирования, могут быть баги и ошибки. В случае предложений или ошибок, контакт для связи: @not_salieri"
        ])

        await message.reply_text(
            "\n".join(help_text),
            quote=True
        )

    except Exception as e:
        log.error("Error handling help command", error=str(e))
        await message.reply_text(
            "❌ Произошла ошибка при получении списка команд",
            quote=True
        )
