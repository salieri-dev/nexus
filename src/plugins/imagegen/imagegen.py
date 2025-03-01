"""Image generation command handler."""

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from structlog import get_logger
from typing import Dict, Any, List

from src.plugins.help import command_handler
from .constants import CALLBACK_PREFIX, MODEL_CALLBACK, NEGATIVE_PROMPT_CALLBACK, CFG_SCALE_CALLBACK, LORAS_CALLBACK, SCHEDULER_CALLBACK, IMAGE_SIZE_CALLBACK, BACK_CALLBACK, AVAILABLE_MODELS, AVAILABLE_LORAS, AVAILABLE_SCHEDULERS, IMAGE_SIZES
from .repository import ImagegenRepository, ImagegenModelRepository
from .service import ImagegenService

log = get_logger(__name__)

# Initialize the image generation service once at the module level
imagegen_service = ImagegenService()


async def create_settings_keyboard(config: Dict[str, Any]) -> InlineKeyboardMarkup:
    """
    Create the main settings keyboard.

    Args:
        config: Current imagegen configuration

    Returns:
        InlineKeyboardMarkup with settings buttons
    """
    # We'll load models and loras only when needed, not on every keyboard creation

    # Get current values for display
    current_model = next((name for name, value in AVAILABLE_MODELS.items() if value == config.get("model")), "Не выбрано")

    current_scheduler = next((name for name, value in AVAILABLE_SCHEDULERS.items() if value == config.get("scheduler")), "Не выбрано")

    current_size = IMAGE_SIZES.get(config.get("image_size", "square_hd"), "Не выбрано")

    # Create keyboard
    keyboard = [
        [InlineKeyboardButton(f"🖼 Модель: {current_model}", callback_data=f"{MODEL_CALLBACK}list")],
        [InlineKeyboardButton(f"🚫 Негативный промпт", callback_data=NEGATIVE_PROMPT_CALLBACK)],
        [InlineKeyboardButton(f"⚙️ CFG Scale: {config.get('cfg_scale', 7.0)}", callback_data=CFG_SCALE_CALLBACK)],
        [InlineKeyboardButton(f"🧩 Loras", callback_data=f"{LORAS_CALLBACK}list")],
        [InlineKeyboardButton(f"🔄 Scheduler: {current_scheduler}", callback_data=f"{SCHEDULER_CALLBACK}list")],
        [InlineKeyboardButton(f"📏 Размер изображения: {current_size}", callback_data=f"{IMAGE_SIZE_CALLBACK}list")],
    ]

    return InlineKeyboardMarkup(keyboard)


async def create_model_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with available models."""
    # Load models only if they're not already loaded
    keyboard = []

    # Add a button for each model
    for model_name, model_id in AVAILABLE_MODELS.items():
        keyboard.append([InlineKeyboardButton(model_name, callback_data=f"{MODEL_CALLBACK}{model_id}")])

    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=BACK_CALLBACK)])

    return InlineKeyboardMarkup(keyboard)


async def create_loras_keyboard(selected_loras: List[str]) -> InlineKeyboardMarkup:
    """Create keyboard with available loras."""
    # Load loras only if they're not already loaded
    keyboard = []

    # Add a button for each lora with selection indicator
    for lora_name, lora_id in AVAILABLE_LORAS.items():
        prefix = "✅ " if lora_id in selected_loras else ""
        keyboard.append([InlineKeyboardButton(f"{prefix}{lora_name}", callback_data=f"{LORAS_CALLBACK}{lora_id}")])

    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=BACK_CALLBACK)])

    return InlineKeyboardMarkup(keyboard)


async def create_scheduler_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with available schedulers."""
    keyboard = []

    # Add a button for each scheduler
    for scheduler_name, scheduler_id in AVAILABLE_SCHEDULERS.items():
        keyboard.append([InlineKeyboardButton(scheduler_name, callback_data=f"{SCHEDULER_CALLBACK}{scheduler_id}")])

    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=BACK_CALLBACK)])

    return InlineKeyboardMarkup(keyboard)


async def create_image_size_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with available image sizes."""
    keyboard = []

    # Add a button for each image size
    for size_id, size_name in IMAGE_SIZES.items():
        keyboard.append([InlineKeyboardButton(size_name, callback_data=f"{IMAGE_SIZE_CALLBACK}{size_id}")])

    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=BACK_CALLBACK)])

    return InlineKeyboardMarkup(keyboard)


@Client.on_message(filters.command(["imagegen"]), group=1)
@command_handler(commands=["imagegen"], description="Генерация изображений и настройки", group="Изображения")
async def imagegen_command(client: Client, message: Message):
    """Handler for /imagegen command."""
    try:
        # Check if there's a prompt after the command
        if len(message.command) > 1:
            # Get the prompt from the message
            prompt = " ".join(message.command[1:])

            # Send a processing message
            processing_msg = await message.reply("🔄 **Генерация изображений...**\n\nЭто может занять некоторое время.", parse_mode=ParseMode.MARKDOWN)

            # Initialize the service
            await imagegen_service.initialize()

            # Generate images
            image_urls = await imagegen_service.generate_images(message.chat.id, prompt)

            if not image_urls:
                await processing_msg.edit_text("❌ **Не удалось сгенерировать изображения.**\n\nПожалуйста, попробуйте другой промпт или настройки.", parse_mode=ParseMode.MARKDOWN)
                return

            # Create media group
            caption = f"🖼 **Сгенерированные изображения**\n\nПромпт: `{prompt}`"
            media_group = await imagegen_service.create_media_group(image_urls, caption)

            # Send the media group
            await client.send_media_group(chat_id=message.chat.id, media=media_group, reply_to_message_id=message.id)

            # Delete the processing message
            await processing_msg.delete()
        else:
            # No prompt provided, show settings UI
            # Get current config
            config = await ImagegenRepository.get_imagegen_config(message.chat.id)

            # Create settings keyboard
            keyboard = await create_settings_keyboard(config)

            # Send settings message
            await message.reply("⚙️ **Настройки генерации изображений**\n\nИспользуйте `/imagegen [промпт]` для генерации изображений\nили выберите параметр для настройки:", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error("Error handling imagegen command", error=str(e))
        await message.reply(f"❌ Произошла ошибка: {str(e)}")


@Client.on_callback_query(filters.regex(f"^{CALLBACK_PREFIX}"))
async def handle_imagegen_callback(client: Client, callback_query: CallbackQuery):
    """Handle callbacks from imagegen settings keyboard."""
    try:
        chat_id = callback_query.message.chat.id
        user_id = callback_query.from_user.id
        data = callback_query.data

        # Get current config
        config = await ImagegenRepository.get_imagegen_config(chat_id)

        # Handle back button
        if data == BACK_CALLBACK:
            keyboard = await create_settings_keyboard(config)
            await callback_query.edit_message_text("⚙️ **Настройки генерации изображений**\n\nВыберите параметр для настройки:", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            return

        # Handle model selection
        if data.startswith(MODEL_CALLBACK):
            model_id = data[len(MODEL_CALLBACK) :]

            if model_id == "list":
                # Show model selection keyboard
                keyboard = await create_model_keyboard()
                await callback_query.edit_message_text("🖼 **Выберите модель:**", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            else:
                # Update model setting
                await ImagegenRepository.update_imagegen_setting(chat_id, "model", model_id)

                # Update config and show main settings
                config = await ImagegenRepository.get_imagegen_config(chat_id)
                keyboard = await create_settings_keyboard(config)

                await callback_query.edit_message_text(f"⚙️ **Настройки генерации изображений**\n\n✅ Модель успешно изменена\n\nВыберите параметр для настройки:", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            return

        # Handle negative prompt
        if data == NEGATIVE_PROMPT_CALLBACK:
            # Ask user to send negative prompt
            await callback_query.edit_message_text(f"🚫 **Негативный промпт**\n\nТекущее значение: `{config.get('negative_prompt', '')}`\n\nОтправьте новый негативный промпт в ответ на это сообщение (максимум 512 символов).\n\nДля отмены нажмите /cancel", parse_mode=ParseMode.MARKDOWN)
            return

        # Handle CFG Scale
        if data == CFG_SCALE_CALLBACK:
            # Ask user to send CFG Scale
            await callback_query.edit_message_text(f"⚙️ **CFG Scale**\n\nТекущее значение: `{config.get('cfg_scale', 7.0)}`\n\nОтправьте новое значение CFG Scale в ответ на это сообщение (число с плавающей точкой).\n\nДля отмены нажмите /cancel", parse_mode=ParseMode.MARKDOWN)
            return

        # Handle loras selection
        if data.startswith(LORAS_CALLBACK):
            lora_id = data[len(LORAS_CALLBACK) :]

            if lora_id == "list":
                # Show loras selection keyboard
                keyboard = await create_loras_keyboard(config.get("loras", []))
                await callback_query.edit_message_text("🧩 **Выберите Loras:**\n\nНажмите на Lora для выбора/отмены выбора", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            else:
                # Toggle lora selection
                current_loras = config.get("loras", [])

                if lora_id in current_loras:
                    current_loras.remove(lora_id)
                else:
                    current_loras.append(lora_id)

                # Update loras setting
                await ImagegenRepository.update_imagegen_setting(chat_id, "loras", current_loras)

                # Update config and show loras selection
                config = await ImagegenRepository.get_imagegen_config(chat_id)
                keyboard = await create_loras_keyboard(config.get("loras", []))

                await callback_query.edit_message_text("🧩 **Выберите Loras:**\n\nНажмите на Lora для выбора/отмены выбора", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            return

        # Handle scheduler selection
        if data.startswith(SCHEDULER_CALLBACK):
            scheduler_id = data[len(SCHEDULER_CALLBACK) :]

            if scheduler_id == "list":
                # Show scheduler selection keyboard
                keyboard = await create_scheduler_keyboard()
                await callback_query.edit_message_text("🔄 **Выберите Scheduler:**", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            else:
                # Update scheduler setting
                await ImagegenRepository.update_imagegen_setting(chat_id, "scheduler", scheduler_id)

                # Update config and show main settings
                config = await ImagegenRepository.get_imagegen_config(chat_id)
                keyboard = await create_settings_keyboard(config)

                await callback_query.edit_message_text(f"⚙️ **Настройки генерации изображений**\n\n✅ Scheduler успешно изменен\n\nВыберите параметр для настройки:", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            return

        # Handle image size selection
        if data.startswith(IMAGE_SIZE_CALLBACK):
            size_id = data[len(IMAGE_SIZE_CALLBACK) :]

            if size_id == "list":
                # Show image size selection keyboard
                keyboard = await create_image_size_keyboard()
                await callback_query.edit_message_text("📏 **Выберите размер изображения:**", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            else:
                # Update image size setting
                await ImagegenRepository.update_imagegen_setting(chat_id, "image_size", size_id)

                # Update config and show main settings
                config = await ImagegenRepository.get_imagegen_config(chat_id)
                keyboard = await create_settings_keyboard(config)

                await callback_query.edit_message_text(f"⚙️ **Настройки генерации изображений**\n\n✅ Размер изображения успешно изменен\n\nВыберите параметр для настройки:", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            return

    except Exception as e:
        log.error("Error handling imagegen callback", error=str(e))
        await callback_query.answer("❌ Произошла ошибка при обработке настроек.")


# Message handlers for text input settings
@Client.on_message(filters.reply & ~filters.command(["cancel"]), group=2)
async def handle_imagegen_text_input(client: Client, message: Message):
    """Handle text input for imagegen settings."""
    try:
        # Check if the message is a reply to a bot message about imagegen settings
        if not message.reply_to_message or not message.reply_to_message.from_user or message.reply_to_message.from_user.id != client.me.id:
            return

        # Check if the replied message contains imagegen settings text
        replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""

        # Handle negative prompt input
        if "Негативный промпт" in replied_text and "Отправьте новый негативный промпт" in replied_text:
            # Get the negative prompt from the message
            negative_prompt = message.text.strip()

            # Validate length
            if len(negative_prompt) > 512:
                await message.reply("❌ Негативный промпт слишком длинный (максимум 512 символов).")
                return

            # Update negative prompt setting
            chat_id = message.chat.id
            await ImagegenRepository.update_imagegen_setting(chat_id, "negative_prompt", negative_prompt)

            # Update config and show main settings
            config = await ImagegenRepository.get_imagegen_config(chat_id)
            keyboard = await create_settings_keyboard(config)

            await message.reply(f"⚙️ **Настройки генерации изображений**\n\n✅ Негативный промпт успешно изменен\n\nВыберите параметр для настройки:", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            return

        # Handle CFG Scale input
        if "CFG Scale" in replied_text and "Отправьте новое значение CFG Scale" in replied_text:
            # Get the CFG Scale from the message
            try:
                cfg_scale = float(message.text.strip())

                # Validate range (typical range for CFG Scale)
                if cfg_scale < 1.0 or cfg_scale > 30.0:
                    await message.reply("❌ CFG Scale должен быть в диапазоне от 1.0 до 30.0.")
                    return

                # Update CFG Scale setting
                chat_id = message.chat.id
                await ImagegenRepository.update_imagegen_setting(chat_id, "cfg_scale", cfg_scale)

                # Update config and show main settings
                config = await ImagegenRepository.get_imagegen_config(chat_id)
                keyboard = await create_settings_keyboard(config)

                await message.reply(f"⚙️ **Настройки генерации изображений**\n\n✅ CFG Scale успешно изменен\n\nВыберите параметр для настройки:", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            except ValueError:
                await message.reply("❌ Пожалуйста, введите корректное число с плавающей точкой.")
            return

    except Exception as e:
        log.error("Error handling imagegen text input", error=str(e))
        await message.reply("❌ Произошла ошибка при обработке настроек.")


# Cancel command handler
@Client.on_message(filters.command(["cancel"]), group=3)
async def handle_cancel(client: Client, message: Message):
    """Handle /cancel command for imagegen settings."""
    try:
        # Check if the message is a reply to a bot message about imagegen settings
        if not message.reply_to_message or not message.reply_to_message.from_user or message.reply_to_message.from_user.id != client.me.id:
            return

        # Check if the replied message contains imagegen settings text
        replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""

        if "Негативный промпт" in replied_text or "CFG Scale" in replied_text:
            # Get current config
            chat_id = message.chat.id
            config = await ImagegenRepository.get_imagegen_config(chat_id)

            # Create settings keyboard
            keyboard = await create_settings_keyboard(config)

            # Send settings message
            await message.reply("⚙️ **Настройки генерации изображений**\n\nОперация отменена.\n\nВыберите параметр для настройки:", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        log.error("Error handling cancel command", error=str(e))
        await message.reply("❌ Произошла ошибка при обработке команды отмены.")


# Command to add a new model
@Client.on_message(filters.command(["add_model"]), group=4)
@command_handler(commands=["add_model"], description="Добавить новую модель для генерации изображений", group="Изображения")
async def add_model_command(client: Client, message: Message):
    """Handler for /add_model command."""
    try:
        # Check command format
        command_parts = message.text.split(maxsplit=4)

        if len(command_parts) < 4:
            await message.reply('❌ **Неверный формат команды**\n\nИспользуйте: `/add_model id название_модели URL [описание]`\n\nПример: `/add_model sdxl "Stable Diffusion XL" https://example.com/model.safetensors "Описание модели"`', parse_mode=ParseMode.MARKDOWN)
            return

        # Extract model details
        model_id = command_parts[1].strip("\"'").lower()
        model_name = command_parts[2].strip("\"'")
        model_url = command_parts[3].strip("\"'")
        model_description = command_parts[4].strip("\"'") if len(command_parts) > 4 else ""

        # Initialize repository
        repo = ImagegenModelRepository()
        await repo.initialize()

        # Add model to database
        await repo.add_model(model_id, model_name, model_url, model_description)

        await message.reply(f"✅ **Модель успешно добавлена**\n\nНазвание: {model_name}\nURL: {model_url}\nОписание: {model_description}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error("Error adding model", error=str(e))
        await message.reply(f"❌ Произошла ошибка при добавлении модели: {str(e)}")


# Command to add a new lora
@Client.on_message(filters.command(["add_lora"]), group=5)
@command_handler(commands=["add_lora"], description="Добавить новую Lora для генерации изображений", group="Изображения")
async def add_lora_command(client: Client, message: Message):
    """Handler for /add_lora command."""
    try:
        # Check command format
        command_parts = message.text.split(maxsplit=4)

        if len(command_parts) < 4:
            await message.reply('❌ **Неверный формат команды**\n\nИспользуйте: `/add_lora id название_lora URL [описание]`\n\nПример: `/add_lora detail_xl "Add Detail XL" https://example.com/lora.safetensors "Описание lora"`', parse_mode=ParseMode.MARKDOWN)
            return

        # Extract lora details
        lora_id = command_parts[1].strip("\"'").lower()
        lora_name = command_parts[2].strip("\"'")
        lora_url = command_parts[3].strip("\"'")
        lora_description = command_parts[4].strip("\"'") if len(command_parts) > 4 else ""

        # Initialize repository
        repo = ImagegenModelRepository()
        await repo.initialize()

        # Add lora to database
        await repo.add_lora(lora_id, lora_name, lora_url, lora_description)

        await message.reply(f"✅ **Lora успешно добавлена**\n\nНазвание: {lora_name}\nURL: {lora_url}\nОписание: {lora_description}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error("Error adding lora", error=str(e))
        await message.reply(f"❌ Произошла ошибка при добавлении lora: {str(e)}")


# Command to list all models
@Client.on_message(filters.command(["list_models"]), group=6)
@command_handler(commands=["list_models"], description="Показать список доступных моделей", group="Изображения")
async def list_models_command(client: Client, message: Message):
    """Handler for /list_models command."""
    try:
        # Initialize repository
        repo = ImagegenModelRepository()
        await repo.initialize()

        # Get all models
        models = await repo.get_all_models(active_only=False)

        if not models:
            await message.reply("❌ Нет доступных моделей.")
            return

        # Format models list
        models_text = "📋 **Список доступных моделей:**\n\n"

        for i, model in enumerate(models, 1):
            status = "✅ Активна" if model.get("is_active", True) else "❌ Неактивна"
            description = f"\n   {model.get('description')}" if model.get("description") else ""
            models_text += f"{i}. **{model['name']}** (ID: `{model['id']}`) - {status}{description}\n   URL: `{model['url']}`\n\n"

        await message.reply(models_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error("Error listing models", error=str(e))
        await message.reply(f"❌ Произошла ошибка при получении списка моделей: {str(e)}")


# Command to list all loras
@Client.on_message(filters.command(["list_loras"]), group=7)
@command_handler(commands=["list_loras"], description="Показать список доступных Loras", group="Изображения")
async def list_loras_command(client: Client, message: Message):
    """Handler for /list_loras command."""
    try:
        # Initialize repository
        repo = ImagegenModelRepository()
        await repo.initialize()

        # Get all loras
        loras = await repo.get_all_loras(active_only=False)

        if not loras:
            await message.reply("❌ Нет доступных Loras.")
            return

        # Format loras list
        loras_text = "📋 **Список доступных Loras:**\n\n"

        for i, lora in enumerate(loras, 1):
            status = "✅ Активна" if lora.get("is_active", True) else "❌ Неактивна"
            description = f"\n   {lora.get('description')}" if lora.get("description") else ""
            loras_text += f"{i}. **{lora['name']}** (ID: `{lora['id']}`) - {status}{description}\n   URL: `{lora['url']}`\n\n"

        await message.reply(loras_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error("Error listing loras", error=str(e))
        await message.reply(f"❌ Произошла ошибка при получении списка Loras: {str(e)}")
