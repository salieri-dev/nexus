from pyrogram import Client, filters
from pyrogram.types import Message
from structlog import get_logger

from src.utils.helpers import get_photo
from src.plugins.magik.service import ImageService
from src.plugins.help import command_handler

# Setup logger
log = get_logger(__name__)
image_service = ImageService()

# Initialize message service
MAGIK_NO_IMAGE = "Пожалуйста, предоставьте изображение или GIF, или ответьте на сообщение с изображением или GIF."
MAGIK_GENERATION_FAILED = "Не удалось сгенерировать изображение."
MAGIK_NO_REPLY_IMAGE = "Пожалуйста, предоставьте изображение или ответьте на сообщение с изображением."
GENERAL_ERROR = "Произошла ошибка."


# General helper for commands operating on image + GIF
async def handle_image_command(message: Message, process_func):
    try:
        photo, is_gif = await get_photo(message)
        if not photo:
            await message.reply_text(text=MAGIK_NO_IMAGE, quote=True)
            return

        processed_image = process_func(photo, is_gif)
        if is_gif:
            await message.reply_animation(animation=processed_image, quote=True)
        else:
            await message.reply_photo(photo=processed_image, quote=True)

    except Exception as e:
        log.error(f"Error in image command: {e}", exc_info=True)
        await message.reply_text(text=GENERAL_ERROR, quote=True)


# General helper for commands with variable parameters (like rotate, watermark, jpeg)
async def handle_param_command(message: Message, process_func, default_value=90):
    try:
        photo, is_gif = await get_photo(message)
        if not photo:
            await message.reply_text(text=MAGIK_NO_REPLY_IMAGE, quote=True)
            return

        try:
            param = int(message.text.split()[1])
        except (IndexError, ValueError):
            param = default_value

        processed_image = process_func(photo, param)
        await message.reply_photo(photo=processed_image, quote=True)

    except Exception as e:
        log.error(f"Error in param command: {e}")
        await message.reply_text(text=GENERAL_ERROR, quote=True)


# ---- COMMANDS ----
@command_handler(commands=["magik"], description="Применяет эффект искажения к изображению", group="Изображения")
@Client.on_message(filters.command("magik"), group=2)
async def magik_command(client: Client, message: Message):
    await handle_image_command(message, lambda photo, is_gif: image_service.do_magik(2, photo, is_gif))


@command_handler(commands=["pixel"], description="Пикселизирует изображение", group="Изображения")
@Client.on_message(filters.command("pixel"), group=2)
async def pixel_command(client: Client, message: Message):
    await handle_image_command(message, lambda photo, is_gif: image_service.make_pixel_gif(photo, 9) if is_gif else image_service.make_pixel(photo, 9))


@command_handler(commands=["waaw"], description="Зеркально отражает изображение по вертикали от центра", group="Изображения")
@Client.on_message(filters.command("waaw"), group=2)
async def waaw_command(client: Client, message: Message):
    return await handle_image_command(message, lambda photo, is_gif: image_service.do_waaw(photo))


@command_handler(commands=["haah"], description="Зеркально отражает изображение по горизонтали от центра", group="Изображения")
@Client.on_message(filters.command("haah"), group=2)
async def haah_command(client: Client, message: Message):
    return await handle_image_command(message, lambda photo, is_gif: image_service.do_haah(photo))


@command_handler(commands=["woow"], description="Зеркально отражает верхнюю половину изображения вниз", group="Изображения")
@Client.on_message(filters.command("woow"), group=2)
async def woow_command(client: Client, message: Message):
    return await handle_image_command(message, lambda photo, is_gif: image_service.do_woow(photo))


@command_handler(commands=["hooh"], description="Зеркально отражает левую половину изображения вправо", group="Изображения")
@Client.on_message(filters.command("hooh"), group=2)
async def hooh_command(client: Client, message: Message):
    return await handle_image_command(message, lambda photo, is_gif: image_service.do_hooh(photo))


@command_handler(commands=["flipimg"], description="Переворачивает изображение вертикально", group="Изображения")
@Client.on_message(filters.command("flipimg"), group=2)
async def flipimg_command(client: Client, message: Message):
    return await handle_image_command(message, lambda photo, is_gif: image_service.flip_image(photo))


@command_handler(commands=["flop"], description="Переворачивает изображение горизонтально", group="Изображения")
@Client.on_message(filters.command("flop"), group=2)
async def flop_command(client: Client, message: Message):
    return await handle_image_command(message, lambda photo, is_gif: image_service.flop_image(photo))


@command_handler(commands=["invert"], description="Инвертирует цвета изображения", group="Изображения")
@Client.on_message(filters.command("invert"), group=2)
async def invert_command(client: Client, message: Message):
    return await handle_image_command(message, lambda photo, is_gif: image_service.invert_image(photo))


@command_handler(commands=["rotate"], description="Поворачивает изображение на указанный угол", arguments="[угол поворота; по умолчанию: 90]", group="Изображения")
@Client.on_message(filters.command("rotate"), group=2)
async def rotate_command(client: Client, message: Message):
    return await handle_param_command(message, image_service.rotate_image, default_value=90)
