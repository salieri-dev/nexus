"""
GDPR plugin for handling user data deletion requests.
Provides a command to soft-delete all user messages by moving them to a history collection.
"""

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.message_repository import MessageRepository
from src.plugins.help import command_handler

log = get_logger(__name__)

# Callback data prefix to identify GDPR-related callbacks
GDPR_CALLBACK_PREFIX = "gdpr_"
CONFIRM_DELETE_CALLBACK = f"{GDPR_CALLBACK_PREFIX}confirm_delete"
CANCEL_DELETE_CALLBACK = f"{GDPR_CALLBACK_PREFIX}cancel_delete"


@Client.on_message(filters.command("gdpr_delete"), group=1)
@command_handler(commands=["gdpr_delete"], description="Удалить все ваши сообщения из базы данных (GDPR)", group="Утилиты")
async def gdpr_delete_command(client: Client, message: Message):
    """
    Handle the /gdpr_delete command to initiate the GDPR data deletion process.
    Shows a confirmation message with buttons to confirm or cancel.
    """
    try:
        user_id = message.from_user.id
        user_name = message.from_user.first_name

        # Create confirmation keyboard
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Подтвердить удаление", callback_data=CONFIRM_DELETE_CALLBACK), InlineKeyboardButton("❌ Отмена", callback_data=CANCEL_DELETE_CALLBACK)]])

        # Send confirmation message
        await message.reply(
            f"⚠️ **ВНИМАНИЕ!** ⚠️\n\nВы запросили удаление всех ваших сообщений из базы данных бота.\n\n• Это действие **нельзя отменить**\n• Сообщения будут перемещены в архивную коллекцию\n• Они больше не будут доступны через бота\n\nВы уверены, что хотите продолжить?", reply_markup=keyboard, quote=True
        )

    except Exception as e:
        log.error("Error handling gdpr_delete command", error=str(e), user_id=message.from_user.id)
        await message.reply("❌ Произошла ошибка при обработке запроса на удаление данных.", quote=True)


@Client.on_callback_query(filters.regex(f"^{GDPR_CALLBACK_PREFIX}"))
async def handle_gdpr_callback(client: Client, callback_query: CallbackQuery):
    """
    Handle callbacks from GDPR-related inline keyboard buttons.
    """
    try:
        user_id = callback_query.from_user.id
        message_id = callback_query.message.id
        chat_id = callback_query.message.chat.id

        # Check if this is the user who initiated the command
        if callback_query.message.reply_to_message and callback_query.message.reply_to_message.from_user.id != user_id:
            await callback_query.answer("Вы не можете использовать эту кнопку, так как не вы инициировали команду.", show_alert=True)
            return

        # Handle confirmation
        if callback_query.data == CONFIRM_DELETE_CALLBACK:
            await callback_query.edit_message_text("⏳ Удаление ваших сообщений... Пожалуйста, подождите.")

            # Initialize repository
            db_client = DatabaseClient.get_instance()
            message_repo = MessageRepository(db_client.client)

            # Perform soft-delete
            deleted_count = await message_repo.soft_delete_user_messages(user_id)

            # Update message with result
            await callback_query.edit_message_text(f"✅ **Удаление завершено**\n\nУдалено сообщений: {deleted_count}\n\nВаши сообщения были перемещены в архивную коллекцию и больше не доступны через бота.")

        # Handle cancellation
        elif callback_query.data == CANCEL_DELETE_CALLBACK:
            await callback_query.edit_message_text("❌ **Удаление отменено**\n\nВаши сообщения остались без изменений.")

        else:
            # Unknown callback data
            await callback_query.answer("Неизвестное действие")

    except Exception as e:
        log.error("Error handling GDPR callback", error=str(e), user_id=user_id)
        await callback_query.edit_message_text("❌ Произошла ошибка при обработке запроса на удаление данных.")
