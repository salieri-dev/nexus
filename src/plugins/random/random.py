import random
from typing import List

from pyrogram import Client, filters
from pyrogram.types import Message
from structlog import get_logger

from src.plugins.help import command_handler

# Setup logger
log = get_logger(__name__)

# Magic 8-ball responses in Russian
MAGIC_8BALL_RESPONSES = [
    "Бесспорно",
    "Предрешено",
    "Никаких сомнений",
    "Определённо да",
    "Можешь быть уверен в этом",
    "Мне кажется — «да»",
    "Вероятнее всего",
    "Хорошие перспективы",
    "Знаки говорят — «да»",
    "Да",
    "Пока не ясно, попробуй снова",
    "Спроси позже",
    "Лучше не рассказывать",
    "Сейчас нельзя предсказать",
    "Сконцентрируйся и спроси опять",
    "Даже не думай",
    "Мой ответ — «нет»",
    "По моим данным — «нет»",
    "Перспективы не очень хорошие",
    "Весьма сомнительно",
]


@command_handler(commands=["choice"], description="Выбрать случайный вариант из списка", arguments="[варианты через ;]", group="Рандом")
@Client.on_message(filters.command("choice"), group=2)
async def choice_command(client: Client, message: Message):
    """
    Choose a random option from a list separated by semicolons
    """
    try:
        # Get the text after the command
        command_parts = message.text.split(maxsplit=1)

        if len(command_parts) < 2:
            await message.reply_text("Пожалуйста, укажите варианты через точку с запятой (;)", quote=True)
            return

        options_text = command_parts[1]
        options = [option.strip() for option in options_text.split(";") if option.strip()]

        if not options:
            await message.reply_text("Не удалось найти варианты. Укажите их через точку с запятой (;)", quote=True)
            return

        chosen_option = random.choice(options)
        await message.reply_text(f"🎲 {chosen_option}", quote=True)

    except Exception as e:
        log.error(f"Error in choice command: {e}")
        await message.reply_text("Произошла ошибка при выборе варианта.", quote=True)


@command_handler(commands=["roll"], description="Бросить кубик", group="Рандом")
@Client.on_message(filters.command("roll"), group=2)
async def roll_command(client: Client, message: Message):
    """
    Roll a dice (1-6)
    """
    try:
        result = random.randint(1, 6)
        await message.reply_text(f"🎲 {result}", quote=True)
    except Exception as e:
        log.error(f"Error in roll command: {e}")
        await message.reply_text("Произошла ошибка при броске кубика.", quote=True)


@command_handler(commands=["flip"], description="Подбросить монетку", group="Рандом")
@Client.on_message(filters.command("flip"), group=2)
async def flip_command(client: Client, message: Message):
    """
    Flip a coin
    """
    try:
        result = random.choice(["Орёл", "Решка"])
        await message.reply_text(f"🪙 {result}", quote=True)
    except Exception as e:
        log.error(f"Error in flip command: {e}")
        await message.reply_text("Произошла ошибка при подбрасывании монетки.", quote=True)


@command_handler(commands=["8ball"], description="Магический шар предсказаний", group="Рандом")
@Client.on_message(filters.command("8ball"), group=2)
async def magic_8ball_command(client: Client, message: Message):
    """
    Magic 8-ball predictions
    """
    try:
        response = random.choice(MAGIC_8BALL_RESPONSES)
        await message.reply_text(f"🔮 {response}", quote=True)
    except Exception as e:
        log.error(f"Error in 8ball command: {e}")
        await message.reply_text("Произошла ошибка при обращении к магическому шару.", quote=True)


@command_handler(commands=["random"], description="Случайное число в диапазоне", arguments="[мин] [макс]", group="Рандом")
@Client.on_message(filters.command("random"), group=2)
async def random_command(client: Client, message: Message):
    """
    Generate a random number in a range
    """
    try:
        command_parts = message.text.split()

        # Default range
        min_value = 1
        max_value = 100

        # Parse arguments
        if len(command_parts) >= 3:
            try:
                min_value = int(command_parts[1])
                max_value = int(command_parts[2])
            except ValueError:
                await message.reply_text("Пожалуйста, укажите числовые значения для диапазона.", quote=True)
                return
        elif len(command_parts) == 2:
            try:
                max_value = int(command_parts[1])
            except ValueError:
                await message.reply_text("Пожалуйста, укажите числовое значение для максимума.", quote=True)
                return

        # Ensure min is less than max
        if min_value > max_value:
            min_value, max_value = max_value, min_value

        result = random.randint(min_value, max_value)
        await message.reply_text(f"🎲 ({min_value}-{max_value}): {result}", quote=True)

    except Exception as e:
        log.error(f"Error in random command: {e}")
        await message.reply_text("Произошла ошибка при генерации случайного числа.", quote=True)
