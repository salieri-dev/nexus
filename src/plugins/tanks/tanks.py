import random
from typing import Dict

from pyrogram import Client, filters
from pyrogram.types import Message
import structlog
from src.database.client import DatabaseClient

from src.plugins.tanks.tanks_repository import TanksRepository

logger = structlog.get_logger()

# Message constants
TANK_INVALID_TIER_MESSAGE = "❌ Ранг должен быть числом от 1 до 11"
TANK_NOT_FOUND_MESSAGE = "❌ Увы, ничего не нашлось"
GENERAL_ERROR_MESSAGE = "❌ Произошла ошибка при обработке запроса. Повторите попытку позже."

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


@Client.on_message(filters.command(["tanks"]), group=1)
async def tanks(client, message: Message):
    """Handle /tanks command with various options:
    - /tanks -> random tank
    - /tanks <tier> -> tanks of specific tier
    - /tanks <name> -> search tank by name
    """
    try:
        # Get database instance and initialize repository
        db = DatabaseClient.get_instance()
        repository = TanksRepository(db.client)

        # Get command arguments
        args = message.command[1:]

        # Case 1: No arguments - return random tank
        if not args:
            tank = await repository.get_random_tank()
            if not tank:
                await message.reply(TANK_NOT_FOUND_MESSAGE)
                return
            return await format_tank_response(message, tank)

        # Case 2: Numeric argument - get tanks by tier
        if args[0].isdigit():
            tier = int(args[0])
            if not 1 <= tier <= 11:
                await message.reply(TANK_INVALID_TIER_MESSAGE)
                return

            tanks = await repository.get_tanks_by_tier(tier)
            if not tanks:
                await message.reply(TANK_NOT_FOUND_MESSAGE)
                return

            # Return a random tank from the tier
            tank = random.choice(tanks)
            return await format_tank_response(message, tank)

        # Case 3: Text argument - search tank by name
        search_query = " ".join(args)
        tanks = await repository.search_tanks_by_name(search_query)

        if not tanks:
            await message.reply("Не нашёл такого танка")
            return

        # Return the first matched tank
        return await format_tank_response(message, tanks[0])

    except Exception as e:
        logger.error("Error in tanks command", error=str(e))
        await message.reply(GENERAL_ERROR_MESSAGE)


async def format_tank_response(message: Message, tank: Dict) -> None:
    """Format and send tank information response with markdown"""
    tank_type = TANK_TYPES.get(tank.get("type", ""), "Неизвестный тип")
    nation = NATIONS.get(tank.get("nation", ""), "Неизвестная нация")

    # Format price display
    price = tank.get("price", 0)
    gold_price = tank.get("gold_price", 0)
    price_display = []
    if price > 0:
        price_display.append(f"{price:,} 💰")
    if gold_price > 0:
        price_display.append(f"{gold_price:,} 🪙")
    price_str = " или ".join(price_display) if price_display else "Нет в продаже"

    response = (
        f"**{tank['name']}**\n\n"
        f"🎯 **Тип:** {tank_type}\n"
        f"🌍 **Нация:** {nation}\n"
        f"📊 **Уровень:** {tank.get('tier', 'Неизвестно')}\n"
        f"💳 **Стоимость:** {price_str}\n"
        f"🏪 **Доступность:** {'Недоступен в магазине' if tank.get('not_in_shop') else 'Доступен в магазине'}\n"
    )

    if tank.get("short_name") and tank["short_name"] != tank["name"]:
        response = f"{response}\n📝 **Краткое название:** {tank['short_name']}"

    # Send response with tank image if available
    image_url = tank.get("image_url")
    if image_url:
        await message.reply_photo(
            image_url,
            caption=response
        )
    else:
        await message.reply(
            response
        )
