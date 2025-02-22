import random

from pyrogram import Client, filters
from pyrogram.types import Message
import structlog

from src.plugins.tanks.tanks_repository import TanksRepository

logger = structlog.get_logger()

# Message constants
TANK_INVALID_TIER_MESSAGE = "Tier должен быть от 1 до 11"
TANK_INVALID_TIER_NUMBER_MESSAGE = "Tier должен быть числом от 1 до 11"
TANK_NOT_FOUND_MESSAGE = "Танки не найдены"
GENERAL_ERROR_MESSAGE = "❌ Произошла ошибка при обработке запроса"

# Map of nations to their proper display names
NATIONS = {
    "china": "Китай",
    "czech": "Чехословакия",
    "france": "Франция",
    "germany": "Германия",
    "italy": "Италия",
    "japan": "Япония",
    "poland": "Польша",
    "sweden": "Швеция",
    "uk": "Великобритания",
    "usa": "США",
    "ussr": "СССР"
}

# Map of tank types to display names
TANK_TYPES = {
    "heavy": "Тяжелый танк",
    "light": "Легкий танк",
    "medium": "Средний танк",
    "spg": "Артиллерия 🌈",
    "td": "ПТ-САУ"
}


@Client.on_message(filters.command(["random_tank", "tanks"]), group=1)
async def random_tank_command(client, message):
    """Handle /random_tank command to get random tank, optionally filtered by tier"""
    return