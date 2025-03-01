"""Image generation command handler."""

from typing import Dict, Any, List

from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from structlog import get_logger

from src.plugins.help import command_handler
from src.database.client import DatabaseClient
from src.database.repository.ratelimit_repository import RateLimitRepository
from .constants import CALLBACK_PREFIX, MODEL_CALLBACK, NEGATIVE_PROMPT_CALLBACK, CFG_SCALE_CALLBACK, LORAS_CALLBACK, SCHEDULER_CALLBACK, IMAGE_SIZE_CALLBACK, BACK_CALLBACK, AVAILABLE_SCHEDULERS, IMAGE_SIZES
from .repository import ImagegenRepository, ImagegenModelRepository
from .service import ImagegenService

import httpx
import re

from src.utils.helpers import is_developer


log = get_logger(__name__)

# Initialize the image generation service and repositories
imagegen_service = ImagegenService()
model_repository = ImagegenModelRepository()


async def create_settings_keyboard(config: Dict[str, Any]) -> InlineKeyboardMarkup:
    """
    Create the main settings keyboard.

    Args:
        config: Current imagegen configuration

    Returns:
        InlineKeyboardMarkup with settings buttons
    """
    # Get current values for display
    current_model_id = config.get("model")
    current_model_name = current_model_id  # Default to ID if name can't be found
    
    # Try to get the model name from the repository
    if current_model_id:
        model_data = await model_repository.get_model_by_id(current_model_id)
        if model_data and "name" in model_data:
            current_model_name = model_data["name"]

    current_scheduler = next((name for name, value in AVAILABLE_SCHEDULERS.items() if value == config.get("scheduler")), "Не выбрано")

    current_size = IMAGE_SIZES.get(config.get("image_size", "square_hd"), "Не выбрано")

    # Create keyboard
    keyboard = [
        [InlineKeyboardButton(f"🖼 Модель: {current_model_name}", callback_data=f"{MODEL_CALLBACK}list")],
        [InlineKeyboardButton(f"🚫 Негативный промпт", callback_data=NEGATIVE_PROMPT_CALLBACK)],
        [InlineKeyboardButton(f"⚙️ CFG Scale: {config.get('cfg_scale', 7.0)}", callback_data=CFG_SCALE_CALLBACK)],
        [InlineKeyboardButton(f"🧩 Loras", callback_data=f"{LORAS_CALLBACK}list")],
        [InlineKeyboardButton(f"🔄 Scheduler: {current_scheduler}", callback_data=f"{SCHEDULER_CALLBACK}list")],
        [InlineKeyboardButton(f"📏 Размер изображения: {current_size}", callback_data=f"{IMAGE_SIZE_CALLBACK}list")],
    ]

    return InlineKeyboardMarkup(keyboard)


async def create_model_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with available models."""
    keyboard = []

    # Fetch models directly from the repository
    models = await model_repository.get_all_models(active_only=True)
    
    # Add a button for each model
    for model in models:
        model_id = model["id"]
        model_name = model["name"]
        keyboard.append([InlineKeyboardButton(model_name, callback_data=f"{MODEL_CALLBACK}{model_id}")])

    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=BACK_CALLBACK)])

    return InlineKeyboardMarkup(keyboard), models


async def create_loras_keyboard(selected_loras: List[str]) -> InlineKeyboardMarkup:
    """Create keyboard with available loras."""
    keyboard = []

    # Fetch loras directly from the repository
    loras = await model_repository.get_all_loras(active_only=True)
    
    # Add a button for each lora with selection indicator
    for lora in loras:
        lora_id = lora["id"]
        lora_name = lora["name"]
        prefix = "✅ " if lora_id in selected_loras else ""
        keyboard.append([InlineKeyboardButton(f"{prefix}{lora_name}", callback_data=f"{LORAS_CALLBACK}{lora_id}")])

    # Add back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=BACK_CALLBACK)])

    return InlineKeyboardMarkup(keyboard), loras


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
@command_handler(commands=["imagegen"], description="Генерация изображений и настройки", group="Нейронки")
async def imagegen_command(client: Client, message: Message):
    """Handler for /imagegen command."""
    try:
        # Check if there's a prompt after the command
        if len(message.command) > 1:
            # Apply rate limiting only for image generation
            # Check rate limit manually
            user_id = message.from_user.id
            
            # Developer bypass - allow owner to bypass rate limits
            if is_developer(user_id):
                log.info("Developer bypassed rate limit for imagegen", user_id=user_id)
            else:
                db_client = DatabaseClient.get_instance()
                rate_limit_repo = RateLimitRepository(db_client)
                
                # Check if user is rate limited (3 minutes window)
                allowed = await rate_limit_repo.check_rate_limit(
                    user_id=user_id,
                    operation="imagegen",
                    window_seconds=180  # 3 minutes
                )
                
                if not allowed:
                    await message.reply(
                        "⏳ **Слишком много запросов!**\n\nПожалуйста, подождите 3 минуты перед следующей генерацией изображений.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
            # Get the prompt from the message
            prompt = " ".join(message.command[1:])

            # Send a processing message
            processing_msg = await message.reply("🔄 **Генерация изображений...**\n\nЭто может занять некоторое время.", parse_mode=ParseMode.MARKDOWN)

            # Initialize the service
            await imagegen_service.initialize()

            # Get the user's configuration instead of the chat's configuration
            user_config = await ImagegenRepository.get_imagegen_config(user_id)
            
            # Log the configuration being used
            log.info("Using user's imagegen config", user_id=user_id, config=user_config)
            
            # Generate images using the user's configuration
            image_urls = await imagegen_service.generate_images(user_id, prompt)

            if not image_urls:
                await processing_msg.edit_text("❌ **Не удалось сгенерировать изображения.**\n\nПожалуйста, попробуйте другой промпт или настройки.", parse_mode=ParseMode.MARKDOWN)
                return

            # Get model information
            model_id = user_config.get("model", "")
            model_name = model_id  # Default to ID if name can't be found
            if model_id:
                model_data = await model_repository.get_model_by_id(model_id)
                if model_data and "name" in model_data:
                    model_name = model_data["name"]
            
            # Get scheduler information
            scheduler_id = user_config.get("scheduler", "")
            scheduler_name = next((name for name, value in AVAILABLE_SCHEDULERS.items() if value == scheduler_id), "Unknown")
            
            # Get image size
            image_size = IMAGE_SIZES.get(user_config.get("image_size", "square_hd"), "Unknown")
            
            # Get LoRA information
            lora_names = []
            for lora_id in user_config.get("loras", []):
                lora_data = await model_repository.get_lora_by_id(lora_id)
                if lora_data and "name" in lora_data:
                    lora_names.append(lora_data["name"])
            lora_info = ", ".join(lora_names) if lora_names else "None"
            
            # Get the actual payload that was sent to the API
            payload = await imagegen_service._prepare_generation_payload(user_id, prompt)
            
            # Create comprehensive caption with all settings
            # Get model name from repository
            model_id = user_config.get("model", "")
            model_name = model_id  # Default to ID if name can't be found
            if model_id:
                model_data = await model_repository.get_model_by_id(model_id)
                if model_data and "name" in model_data:
                    model_name = model_data["name"]
            
            # Get LoRA information with names
            loras_info = []
            for lora in payload['loras']:
                # Use the lora_name directly from the payload if available
                lora_name = lora.get('lora_name', 'Unknown LoRA')
                lora_weight = lora.get('weight', 0.7)
                
                # If lora_name is not available, try to get it from the repository
                if lora_name == 'Unknown LoRA':
                    lora_id = lora.get('lora_id', '')
                    if not lora_id:
                        # Try to extract ID from path as fallback
                        lora_id = lora.get('path', '').split('/')[-1]
                    
                    # Try to get the LoRA data from the repository
                    try:
                        lora_data = await model_repository.get_lora_by_id(lora_id)
                        if lora_data and "name" in lora_data:
                            lora_name = lora_data["name"]
                        else:
                            # Log that we couldn't find the LoRA name
                            log.warning(f"Could not find LoRA name for ID: {lora_id}")
                    except Exception as e:
                        log.error(f"Error getting LoRA data for ID {lora_id}: {str(e)}")
                
                loras_info.append(f"{lora_name} (weight: {lora_weight})")
                
            caption = (
                f"🖼 **Сгенерированные изображения**\n\n"
                f"**Промпт:** `{payload['prompt']}`\n"
                f"**Негативный промпт:** `{payload['negative_prompt']}`\n\n"
                f"**Модель:** {model_name}\n"
                f"**LoRAs:** {', '.join(loras_info) if loras_info else 'None'}\n"
                f"**CFG Scale:** {payload['guidance_scale']}\n"
                f"**Scheduler:** {payload['scheduler']}\n"
                f"**Размер:** {IMAGE_SIZES.get(payload['image_size'], payload['image_size'])}\n"
                f"**Clip Skip:** {payload.get('clip_skip', 'N/A')}\n"
                f"**Шаги:** {payload.get('num_inference_steps', 'N/A')}\n"
            )

            # Create media group
            media_group = await imagegen_service.create_media_group(image_urls, caption)

            # Send the media group
            await client.send_media_group(chat_id=message.chat.id, media=media_group, reply_to_message_id=message.id)

            # Delete the processing message
            await processing_msg.delete()
        else:
            # Only allow settings UI in private chats
            if message.chat.type != ChatType.PRIVATE:
                await message.reply("⚙️ **Настройки генерации изображений доступны только в личных сообщениях с ботом**\n\nИспользуйте `/imagegen [промпт]` для генерации изображений в этом чате.", parse_mode=ParseMode.MARKDOWN)
                return
                
            # No prompt provided, show settings UI in private chat
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
            # Create new settings keyboard
            keyboard = await create_settings_keyboard(config)
            
            # Edit the message with the settings
            await callback_query.edit_message_text(
                "⚙️ **Настройки генерации изображений**\n\nВыберите параметр для настройки:",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Handle model selection
        if data.startswith(MODEL_CALLBACK):
            model_id = data[len(MODEL_CALLBACK):]

            if model_id == "list":
                # Show model selection keyboard
                keyboard, models = await create_model_keyboard()
                
                # Edit the original message instead of deleting it
                await callback_query.edit_message_text(
                    "👇 **Выберите модель из списка ниже:**",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Prepare model information as text
                preview_message = "**Доступные модели:**\n\n"
                for i, model in enumerate(models, 1):
                    model_text = f"**[{i}] {model['name']}**\n"
                    if model.get("description"):
                        desc = model.get("description", "")
                        if len(desc) > 100:
                            desc = desc[:100] + "..."
                        model_text += f"{desc}\n"
                    model_text += "\n"
                    preview_message += model_text
                
                # Create media group with caption on first image
                media_group = []
                models_with_preview = [model for model in models if model.get("preview_url")]
                
                if models_with_preview:
                    # Add first model with caption
                    media_group.append(
                        InputMediaPhoto(
                            media=models_with_preview[0]["preview_url"],
                            caption=preview_message,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    )
                    
                    # Add remaining models without caption
                    for model in models_with_preview[1:]:
                        media_group.append(
                            InputMediaPhoto(
                                media=model["preview_url"]
                            )
                        )
                    
                    # Send in chunks of 10 (Telegram limit)
                    for i in range(0, len(media_group), 10):
                        chunk = media_group[i:i+10]
                        await client.send_media_group(
                            chat_id=chat_id,
                            media=chunk
                        )
                else:
                    # If no models have preview images, just send the text
                    await client.send_message(
                        chat_id=chat_id,
                        text=preview_message,
                        parse_mode=ParseMode.MARKDOWN
                    )
            else:
                # Update model setting
                await ImagegenRepository.update_imagegen_setting(chat_id, "model", model_id)

                # Return to main settings
                config = await ImagegenRepository.get_imagegen_config(chat_id)
                keyboard = await create_settings_keyboard(config)

                await callback_query.edit_message_text(
                    f"⚙️ **Настройки генерации изображений**\n\n✅ Модель успешно изменена\n\nВыберите параметр для настройки:", 
                    reply_markup=keyboard, 
                    parse_mode=ParseMode.MARKDOWN
                )
            return

        # Handle negative prompt
        if data == NEGATIVE_PROMPT_CALLBACK:
            # Ask user to send negative prompt
            await callback_query.edit_message_text(
                f"🚫 **Негативный промпт**\n\nТекущее значение: `{config.get('negative_prompt', '')}`\n\n" +
                "Отправьте новый негативный промпт в ответ на это сообщение (максимум 512 символов).\n\n" +
                "Для отмены нажмите /cancel", 
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Handle CFG Scale
        if data == CFG_SCALE_CALLBACK:
            # Ask user to send CFG Scale
            await callback_query.edit_message_text(
                f"⚙️ **CFG Scale**\n\nТекущее значение: `{config.get('cfg_scale', 7.0)}`\n\n" +
                "Отправьте новое значение CFG Scale в ответ на это сообщение (число с плавающей точкой).\n\n" +
                "Для отмены нажмите /cancel", 
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Handle loras selection
        if data.startswith(LORAS_CALLBACK):
            lora_id = data[len(LORAS_CALLBACK):]

            if lora_id == "list":
                # Show loras selection keyboard with previews
                keyboard, loras = await create_loras_keyboard(config.get("loras", []))
                
                # Edit the original message instead of deleting it
                await callback_query.edit_message_text(
                    "👇 **Выберите Lora из списка ниже (можно выбрать только одну):**",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Prepare preview data
                preview_message = "**Доступные LoRAs:**\n\n"
                for i, lora in enumerate(loras, 1):
                    selection_status = "✅ " if lora["id"] in config.get("loras", []) else ""
                    lora_text = f"**[{i}] {selection_status}{lora['name']}**\n"
                    if lora.get("trigger_words"):
                        lora_text += f"Trigger words: `{lora['trigger_words']}`\n"
                    lora_text += f"Default scale: {lora.get('default_scale', 0.7)}\n"
                    if lora.get("description"):
                        desc = lora.get("description", "")
                        if len(desc) > 100:
                            desc = desc[:100] + "..."
                        lora_text += f"{desc}\n"
                    lora_text += "\n"
                    preview_message += lora_text
                
                # Create media group with caption on first image
                media_group = []
                loras_with_preview = [lora for lora in loras if lora.get("preview_url")]
                
                if loras_with_preview:
                    # Add first lora with caption
                    media_group.append(
                        InputMediaPhoto(
                            media=loras_with_preview[0]["preview_url"],
                            caption=preview_message,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    )
                    
                    # Add remaining loras without caption
                    for lora in loras_with_preview[1:]:
                        media_group.append(
                            InputMediaPhoto(
                                media=lora["preview_url"]
                            )
                        )
                    
                    # Send in chunks of 10 (Telegram limit)
                    for i in range(0, len(media_group), 10):
                        chunk = media_group[i:i+10]
                        await client.send_media_group(
                            chat_id=chat_id,
                            media=chunk
                        )
                else:
                    # If no loras have preview images, just send the text
                    await client.send_message(
                        chat_id=chat_id,
                        text=preview_message,
                        parse_mode=ParseMode.MARKDOWN
                    )
            else:
                # Replace current lora selection with the new one (only one allowed)
                current_loras = config.get("loras", [])
                
                # If the same lora is clicked again, deselect it
                if lora_id in current_loras:
                    new_loras = []
                else:
                    # Otherwise, select only this lora
                    new_loras = [lora_id]

                # Update loras setting
                await ImagegenRepository.update_imagegen_setting(chat_id, "loras", new_loras)

                # Get updated config
                config = await ImagegenRepository.get_imagegen_config(chat_id)
                
                # Return to main settings immediately after selection
                keyboard = await create_settings_keyboard(config)

                # Update message with success notification and main settings
                status_text = "удалена" if not new_loras else "выбрана"
                await callback_query.edit_message_text(
                    f"⚙️ **Настройки генерации изображений**\n\n✅ Lora {status_text}\n\nВыберите параметр для настройки:", 
                    reply_markup=keyboard, 
                    parse_mode=ParseMode.MARKDOWN
                )
            return

        # Handle scheduler selection
        if data.startswith(SCHEDULER_CALLBACK):
            scheduler_id = data[len(SCHEDULER_CALLBACK):]

            if scheduler_id == "list":
                # Show scheduler selection keyboard
                keyboard = await create_scheduler_keyboard()
                await callback_query.edit_message_text(
                    "🔄 **Выберите Scheduler:**", 
                    reply_markup=keyboard, 
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Update scheduler setting
                await ImagegenRepository.update_imagegen_setting(chat_id, "scheduler", scheduler_id)

                # Update config and show main settings
                config = await ImagegenRepository.get_imagegen_config(chat_id)
                keyboard = await create_settings_keyboard(config)

                await callback_query.edit_message_text(
                    f"⚙️ **Настройки генерации изображений**\n\n✅ Scheduler успешно изменен\n\nВыберите параметр для настройки:", 
                    reply_markup=keyboard, 
                    parse_mode=ParseMode.MARKDOWN
                )
            return

        # Handle image size selection
        if data.startswith(IMAGE_SIZE_CALLBACK):
            size_id = data[len(IMAGE_SIZE_CALLBACK):]

            if size_id == "list":
                # Show image size selection keyboard
                keyboard = await create_image_size_keyboard()
                await callback_query.edit_message_text(
                    "📏 **Выберите размер изображения:**", 
                    reply_markup=keyboard, 
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Update image size setting
                await ImagegenRepository.update_imagegen_setting(chat_id, "image_size", size_id)

                # Update config and show main settings
                config = await ImagegenRepository.get_imagegen_config(chat_id)
                keyboard = await create_settings_keyboard(config)

                await callback_query.edit_message_text(
                    f"⚙️ **Настройки генерации изображений**\n\n✅ Размер изображения успешно изменен\n\nВыберите параметр для настройки:", 
                    reply_markup=keyboard, 
                    parse_mode=ParseMode.MARKDOWN
                )
            return

    except Exception as e:
        log.error("Error handling imagegen callback", error=str(e))
        await callback_query.answer("❌ Произошла ошибка при обработке настроек.")
        
# Command to add a new model from Civitai
@Client.on_message(filters.command(["add_model"]), group=4)
async def add_model_command(client: Client, message: Message):
    """Handler for /add_model command."""
    
    if not is_developer(message.from_user.id):
        await message.reply("❌ **Только разработчик может использовать эту команду**", parse_mode=ParseMode.MARKDOWN)
        return
    
    try:
        # Check command format
        command_parts = message.text.split(maxsplit=1)

        if len(command_parts) < 2:
            await message.reply("❌ **Неверный формат команды**\n\nИспользуйте: `/add_model URL_или_ID`\n\nПример: `/add_model https://civitai.com/models/486237` или `/add_model 486237`", parse_mode=ParseMode.MARKDOWN)
            return

        # Extract model ID from URL or direct ID
        model_input = command_parts[1].strip()
        model_id = None

        # Check if it's a URL or direct ID
        if model_input.isdigit():
            model_id = model_input
        else:
            # Try to extract ID from URL
            url_match = re.search(r"civitai\.com/models/(\d+)", model_input)
            if url_match:
                model_id = url_match.group(1)
            else:
                await message.reply("❌ **Неверный формат URL или ID**\n\nИспользуйте: `/add_model https://civitai.com/models/486237` или `/add_model 486237`", parse_mode=ParseMode.MARKDOWN)
                return

        # Send a processing message
        processing_msg = await message.reply("🔄 **Получение информации о модели с Civitai...**", parse_mode=ParseMode.MARKDOWN)

        # Fetch model data from Civitai API
        async with httpx.AsyncClient() as client:
            api_url = f"https://civitai.com/api/v1/models/{model_id}"
            response = await client.get(api_url)

            if response.status_code != 200:
                await processing_msg.edit_text(f"❌ **Ошибка при получении данных с Civitai API**\n\nСтатус: {response.status_code}", parse_mode=ParseMode.MARKDOWN)
                return

            model_data = response.json()

        # Extract model details
        model_name = model_data.get("name", "Unknown Model")
        model_type = model_data.get("type", "MODEL")
        model_description = model_data.get("description", "")

        # Clean up HTML tags from description
        model_description = re.sub(r"<[^>]+>", "", model_description)
        model_description = model_description[:200] + "..." if len(model_description) > 200 else model_description

        # Get the latest model version
        model_versions = model_data.get("modelVersions", [])
        if not model_versions:
            await processing_msg.edit_text("❌ **Не найдены версии модели**", parse_mode=ParseMode.MARKDOWN)
            return

        latest_version = model_versions[0]

        # Get download URL
        files = latest_version.get("files", [])
        if not files:
            await processing_msg.edit_text("❌ **Не найдены файлы для скачивания**", parse_mode=ParseMode.MARKDOWN)
            return

        primary_file = next((f for f in files if f.get("primary", False)), files[0])
        download_url = primary_file.get("downloadUrl", "")

        if not download_url:
            await processing_msg.edit_text("❌ **Не найден URL для скачивания**", parse_mode=ParseMode.MARKDOWN)
            return

        # Get additional info
        base_model = latest_version.get("baseModel", "Unknown")
        trained_words = latest_version.get("trainedWords", [])
        trigger_words = ", ".join(trained_words) if trained_words else ""

        # Get preview image URL
        preview_url = ""
        images = latest_version.get("images", [])
        if images:
            # Filter for images of type "image" (not video)
            image_type_images = [img for img in images if img.get("type") == "image"]
            if image_type_images:
                # Use the first image of type "image" as preview
                preview_url = image_type_images[0].get("url", "")
            elif images:
                # Fallback to first image if no image type found
                preview_url = images[0].get("url", "")

        # Generate a unique ID
        unique_id = f"{model_type.lower()}_{model_id}".lower()

        # Initialize repository
        repo = ImagegenModelRepository()
        await repo.initialize()

        # Add model to database with appropriate type
        if model_type == "LORA":
            # For LORA type, use add_lora with default scale and trigger words
            default_scale = 0.7
            await repo.add_lora(unique_id, model_name, download_url, model_description, default_scale, trigger_words, model_type, preview_url)
            success_message = f"✅ **Lora успешно добавлена с Civitai**\n\nID: {unique_id}\nНазвание: {model_name}\nТип: {model_type}\nБазовая модель: {base_model}\nTrigger Words: {trigger_words}\nURL: {download_url}\nPreview: {preview_url}\nОписание: {model_description}"
        else:
            # For other types, use add_model
            await repo.add_model(unique_id, model_name, download_url, model_description, model_type, preview_url)
            success_message = f"✅ **Модель успешно добавлена с Civitai**\n\nID: {unique_id}\nНазвание: {model_name}\nТип: {model_type}\nБазовая модель: {base_model}\nURL: {download_url}\nPreview: {preview_url}\nОписание: {model_description}"

        await processing_msg.edit_text(success_message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error("Error adding model from Civitai", error=str(e))
        await message.reply(f"❌ Произошла ошибка при добавлении модели: {str(e)}", parse_mode=ParseMode.MARKDOWN)
