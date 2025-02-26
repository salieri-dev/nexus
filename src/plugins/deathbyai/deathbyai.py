"""Death by AI game command handlers"""
import asyncio

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from structlog import get_logger

from src.database.client import DatabaseClient
from src.plugins.deathbyai.repository import DeathByAIRepository
from src.plugins.deathbyai.service import DeathByAIService
from src.plugins.help import command_handler
from .constants import END_GAME_BUTTON, GAME_EXISTS, GAME_START, GENERAL_ERROR, NO_ACTIVE_GAME, NO_PERMISSION

# Get the shared logger instance
log = get_logger(__name__)

# Initialize repository and service
db_client = DatabaseClient.get_instance()
repository = DeathByAIRepository(db_client.client)
service = DeathByAIService()


async def is_user_authorized(client: Client, chat_id: int, user_id: int, game_initiator_id: int) -> bool:
    """Check if user is authorized to end game"""
    if user_id == game_initiator_id:
        return True

    member = await client.get_chat_member(chat_id, user_id)
    return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]


@command_handler(
    commands=["deathbyai"],
    description="Начать игру Death by AI - попробуй выжить в случайном сценарии",
    group="Games"
)
@Client.on_message(filters.command(["deathbyai"]), group=1)
async def start_game_command(client: Client, message: Message):
    """Start a new Death by AI game"""
    try:
        # Send initial message
        status_msg = await message.reply_text(GAME_START, quote=True)

        # Start new game
        game = await service.start_game(
            repository=repository,
            chat_id=message.chat.id,
            message_id=status_msg.id,
            initiator_id=message.from_user.id
        )

        if not game:
            await status_msg.edit_text(GAME_EXISTS)
            return

        # Create keyboard for ending game
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(END_GAME_BUTTON, callback_data="end_game")
        ]])

        # Send initial game announcement
        message_text, keyboard = service.format_game_message(game)
        await status_msg.edit_text(message_text, reply_markup=keyboard)

        # Start timer update loop
        try:
            while service.get_remaining_time(game) > 0:
                await asyncio.sleep(5)  # Update every 5 seconds

                try:
                    # Get fresh game state
                    game = await repository.get_game_by_message(status_msg.id)
                    if not game or game["status"] != "active":
                        break

                    # Update message with new timer
                    message_text, keyboard = service.format_game_message(game)
                    await status_msg.edit_text(message_text, reply_markup=keyboard)

                except FloodWait as e:
                    # Handle Telegram's flood wait
                    await asyncio.sleep(e.value)
                except Exception as e:
                    log.error("Error updating timer", error=str(e))
                    await asyncio.sleep(5)  # Wait before retry

            # Auto-end game when timer expires
            if game and game["status"] == "active":
                try:
                    # End game and get results
                    final_game = await service.end_game(repository=repository, chat_id=message.chat.id)
                    if final_game:
                        # Send results as new message
                        results = service.format_results(final_game)
                        results_msg = await message.reply_text(results, quote=False)

                        try:
                            # Update original message with game state without button
                            message_text, _ = service.format_game_message(final_game, show_button=False)
                            await status_msg.edit_text(message_text, reply_markup=None)
                        except Exception as e:
                            if "MESSAGE_NOT_MODIFIED" not in str(e):
                                log.error("Error updating game message", error=str(e))

                        try:
                            # Update with end message and link to results
                            end_message = service.format_end_message(final_game, results_msg.id)
                            await status_msg.edit_text(end_message)
                        except Exception as e:
                            if "MESSAGE_NOT_MODIFIED" not in str(e):
                                log.error("Error updating end message", error=str(e))
                    else:
                        await message.reply_text(GENERAL_ERROR, quote=False)
                except Exception as e:
                    log.error("Error sending final results", error=str(e))
                    try:
                        await message.reply_text(GENERAL_ERROR, quote=True)
                    except:
                        pass

        except Exception as e:
            log.error("Error in timer loop", error=str(e))

    except Exception as e:
        log.error("Error starting game", error=str(e))
        await message.reply_text(GENERAL_ERROR, quote=True)


@Client.on_message(filters.reply, group=1)
async def handle_strategy(client: Client, message: Message):
    """Handle strategy submissions"""
    try:
        # Validate reply is to game message
        if not await service.validate_game_message(
                repository=repository,
                message_id=message.reply_to_message.id,
                reply_message_id=message.reply_to_message.id
        ):
            return

        # Submit strategy
        success, response = await service.submit_strategy(
            repository=repository,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            username=message.from_user.mention(),
            strategy=message.text
        )

        if success:
            try:
                # Delete the strategy message
                await message.delete()

                # Get updated game state and refresh the game message
                game = await repository.get_game_by_message(message.reply_to_message.id)
                if game:
                    message_text, keyboard = service.format_game_message(game)
                    await message.reply_to_message.edit_text(
                        message_text,
                        reply_markup=keyboard
                    )
            except Exception as e:
                log.error("Failed to delete messages or update game message", error=str(e))

    except Exception as e:
        log.error("Error handling strategy", error=str(e))
        await message.reply_text(GENERAL_ERROR, quote=True)


@Client.on_callback_query(filters.regex("^end_game$"))
async def end_game_callback(client: Client, callback_query: CallbackQuery):
    """Handle game end button press"""
    try:
        await callback_query.answer()
        message = callback_query.message
        user = callback_query.from_user

        # Get game by message
        game = await repository.get_game_by_message(message.id)
        if not game or game["status"] != "active":
            await callback_query.answer(NO_ACTIVE_GAME)
            return

        # Check if user is authorized to end game
        if not await is_user_authorized(client, message.chat.id, user.id, game["initiator_id"]):
            await callback_query.answer(NO_PERMISSION, show_alert=True)
            return

        # End game and get results
        final_game = await service.end_game(repository=repository, chat_id=message.chat.id)
        if not final_game:
            await message.reply_text(GENERAL_ERROR, quote=False)
            return

        # Send results first to get message ID
        results = service.format_results(final_game)
        results_msg = await message.reply_text(results, quote=False)

        try:
            # Update original message with game state without button
            message_text, _ = service.format_game_message(final_game, show_button=False)
            await message.edit_text(message_text, reply_markup=None)
        except Exception as e:
            if "MESSAGE_NOT_MODIFIED" not in str(e):
                log.error("Error updating game message", error=str(e))

        try:
            # Then update with end message and link
            end_message = service.format_end_message(final_game, results_msg.id)
            await message.edit_text(end_message)
        except Exception as e:
            if "MESSAGE_NOT_MODIFIED" not in str(e):
                log.error("Error updating end message", error=str(e))
        await callback_query.answer("Игра завершена!")

    except Exception as e:
        log.error("Error ending game", error=str(e))
        await callback_query.answer(GENERAL_ERROR, show_alert=True)
