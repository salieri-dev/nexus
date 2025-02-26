"""Service layer for Death by AI game"""
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, Tuple

from pydantic import BaseModel, Field
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository
from src.plugins.deathbyai.repository import DeathByAIRepository
from src.plugins.peer_config.settings import get_chat_setting
from src.services.openrouter import OpenRouter


class DecisionEnum(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class EvaluationResponse(BaseModel):
    """Pydantic model for evaluation response from the AI."""
    decision: DecisionEnum = Field(
        description="Результат попытки выживания - success или failure. Успех - это любой побег или там где игрок выживает полностью без негативных последствий. Иначе - смерть."
    )
    details: str = Field(
        description="Короткий рассказ, объясняющий результат стратегии игрока. Она должна состоять из 2-3 предложений."
    )


log = get_logger(__name__)


class DeathByAIService:
    """Service for managing Death by AI game logic"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeathByAIService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._init_service()
            self._initialized = True

    def _init_service(self) -> None:
        """Initialize service dependencies"""
        self.openrouter = OpenRouter().client
        self.db_client = DatabaseClient.get_instance()
        self.config_repo = BotConfigRepository(self.db_client)

    async def start_game(self, repository: DeathByAIRepository, chat_id: int, message_id: int, initiator_id: int) -> \
            Optional[Dict[str, Any]]:
        """Start a new game if none is active"""
        # Check for active game
        active_game = await repository.get_active_game(chat_id)
        if active_game:
            return None

        # Get random scenario
        scenario = await repository.get_random_scenario()
        if not scenario:
            return None

        # Try to get chat-specific setting first (in seconds)
        game_duration_seconds = await get_chat_setting(
            chat_id,
            "dbai_submission_window",
            60 
        )

        # Add debug logging
        log.info(
            "Game duration set",
            chat_id=chat_id,
            game_duration_seconds=game_duration_seconds,
            custom_setting=game_duration_seconds != 0
        )

        # Create new game with timer
        game = await repository.create_game(
            chat_id=chat_id,
            message_id=message_id,
            scenario=scenario["text"],
            initiator_id=initiator_id,
            end_time=datetime.utcnow() + timedelta(seconds=game_duration_seconds)
        )

        return game

    def get_remaining_time(self, game: Dict[str, Any]) -> int:
        """Get remaining time in seconds"""
        if not game.get("end_time"):
            return 0

        # Calculate remaining time in seconds
        remaining = (game["end_time"] - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))

    def format_game_message(self, game: Dict[str, Any], show_button: bool = True) -> Tuple[
        str, Optional[InlineKeyboardMarkup]]:
        """Format game message with timer and submitted strategies"""
        remaining = self.get_remaining_time(game)
        is_finished = game.get("status") == "finished"

        message = [
            "**🎯 Игра завершена!**" if is_finished else "**🎯 Игра началась!**",
            f"\n**📜 Сценарий:**\n>{game['scenario']}"
        ]

        if not is_finished:
            message.extend([
                "\n**📝 Ответьте на это сообщение вашей стратегией выживания!**",
                f"\n**⏳ Осталось времени:** {remaining // 60}:{remaining % 60:02d}"
            ])

        # Add submitted strategies
        if game.get("players"):
            message.append("\n**👥 Отправленные стратегии:**")
            for player in game["players"]:
                message.append(f"• {player['mention']}")

        keyboard = None
        if not is_finished and show_button and remaining > 5:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("Завершить игру", callback_data="end_game")
            ]])

        return "\n".join(message), keyboard

    async def submit_strategy(self, repository: DeathByAIRepository, chat_id: int, user_id: int, username: str,
                              strategy: str) -> Tuple[bool, str]:
        """Submit a player's strategy for the active game"""
        game = await repository.get_active_game(chat_id)
        if not game:
            return False, "❌ В этом чате нет активной игры"

        # Check if player already submitted
        for player in game["players"]:
            if player["user_id"] == user_id:
                return False, "❌ Вы уже отправили свою стратегию"

        # Add strategy
        success = await repository.add_player_strategy(
            game_id=game["_id"],
            user_id=user_id,
            username=username,
            strategy=strategy
        )

        return success, "✅ Ваша стратегия принята!" if success else "❌ Не удалось сохранить стратегию"

    async def evaluate_strategy(self, scenario: str, strategy: str) -> Optional[Dict[str, str]]:
        """Evaluate a single player's strategy using OpenRouter API"""
        try:
            # Get config values
            model_name = await self.config_repo.get_plugin_config_value("deathbyai", "DEATHBYAI_MODEL_NAME",
                                                                        "anthropic/claude-3.5-sonnet:beta")
            temperature = await self.config_repo.get_plugin_config_value("deathbyai",
                                                                         "DEATHBYAI_EVALUATION_TEMPERATURE", 0.7)

            completion = await self.openrouter.beta.chat.completions.parse(
                messages=[
                    {
                        "role": "system",
                        "content": """You are an AI tasked with evaluating survival strategies in dangerous scenarios. You must respond in valid JSON format with two fields:
1. decision: either "success" or "failure"
2. details: 2-3 sentences explaining the outcome

Example response:
{
    "decision": "success",
    "details": "The player cleverly used their technical knowledge to overcome the AI. By exploiting system vulnerabilities and thinking quickly, they managed to escape without harm."
}"""
                    },
                    {
                        "role": "user",
                        "content": f"""Evaluate this survival scenario and strategy. Respond in JSON format as shown in the example.

Scenario: {scenario}

Player's Strategy: {strategy}

Remember:
- Success means complete escape or survival without negative consequences
- Failure means death or severe negative outcome
- Provide 2-3 sentences explaining the outcome"""
                    }
                ],
                model=model_name,
                temperature=temperature,
                response_format=EvaluationResponse
            )

            # Get the result from the model
            log.info(completion)
            fanfic_response = completion.choices[0].message.parsed
            return fanfic_response

        except Exception as e:
            log.error("Failed to evaluate strategy", error=str(e))

        return None

    async def end_game(self, repository: DeathByAIRepository, chat_id: int) -> Optional[Dict[str, Any]]:
        """End the active game and evaluate all strategies"""
        game = await repository.get_active_game(chat_id)
        if not game:
            return None

        # Mark game as finished
        await repository.update_game_status(game["_id"], "finished")

        # Evaluate each player's strategy
        for player in game["players"]:
            evaluation = await self.evaluate_strategy(game["scenario"], player["strategy"])
            if evaluation:
                await repository.update_player_evaluation(
                    game_id=game["_id"],
                    user_id=player["user_id"],
                    evaluation=evaluation.model_dump()
                )

        # Get updated game state
        return await repository.get_game_by_message(game["message_id"])

    def format_results(self, game: Dict[str, Any]) -> str:
        """Format game results for display"""
        if not game["players"]:
            return "🎯 Игра Death by AI завершена!\n\n❌ Никто не решился взять вызов!"

        survivors = []
        casualties = []

        for player in game["players"]:
            evaluation = player["evaluation"]
            if not evaluation:
                continue

            result_text = (
                f"**{player['mention']}: **"
                f"__{player['strategy']}__\n\n"
                f"**🤖 Вердикт AI:**\n>{evaluation['details']}"
            )

            if evaluation["decision"] == "success":
                survivors.append(result_text)
            else:
                casualties.append(result_text)

        # Build final message
        message = [
            "**🎯 Игра Death by AI завершена!**",
            f"**📜 Сценарий:**\n>{game['scenario']}",
            f"**✨ Выжившие ({len(survivors)}):**"
        ]

        if survivors:
            message.extend(survivors)
        else:
            message.append("Никто не выжил")

        message.append(f"**💀 Погибшие ({len(casualties)}):**")
        if casualties:
            message.extend(casualties)
        else:
            message.append("Нет погибших 🎉")

        return "\n\n".join(message)

    def format_end_message(self, game: Dict[str, Any], results_message_id: int) -> str:
        """Format game end message with scenario and results link"""
        chat_id = str(game["chat_id"]).replace("-100", "")
        results_link = f"https://t.me/c/{chat_id}/{results_message_id}"
        return (
            "🏁 Игра завершена!\n\n"
            f"[Результаты]({results_link})"
        )

    async def validate_game_message(self, repository: DeathByAIRepository, message_id: int,
                                    reply_message_id: int) -> bool:
        """Validate that a reply is to the correct game message"""
        game = await repository.get_game_by_message(message_id)
        return game is not None and game["status"] == "active" and game["message_id"] == reply_message_id
