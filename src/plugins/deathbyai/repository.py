"""Repository for Death by AI game data"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from structlog import get_logger

log = get_logger(__name__)


class DeathByAIRepository:
    """Repository for managing Death by AI game data"""

    def __init__(self, client: AsyncIOMotorClient):
        """Initialize repository with MongoDB client"""
        self.db = client["nexus"]
        self.games = self.db["deathbyai_games"]
        self.scenarios = self.db["deathbyai_scenarios"]

    async def create_indexes(self):
        """Create necessary indexes"""
        # Game indexes
        await self.games.create_index([("chat_id", 1), ("status", 1)])
        await self.games.create_index([("message_id", 1)])
        await self.games.create_index([("initiator_id", 1)])

        # Scenario indexes
        await self.scenarios.create_index([("difficulty", 1)])
        await self.scenarios.create_index([("created_at", -1)])

    async def get_random_scenario(self) -> Optional[Dict[str, Any]]:
        """
        Get a random scenario from the scenarios collection.

        Returns:
            Optional[Dict[str, Any]]: Random scenario document if found, None otherwise
        """
        pipeline = [{"$sample": {"size": 1}}]
        async for scenario in self.scenarios.aggregate(pipeline):
            return scenario
        return None

    async def create_game(self, chat_id: int, message_id: int, scenario: str, initiator_id: int, end_time: datetime) -> Dict[str, Any]:
        """
        Create a new game instance.

        Args:
            chat_id: Chat where game is being created
            message_id: ID of the game announcement message
            scenario: The scenario text
            initiator_id: User ID who started the game
            end_time: When the game should automatically end

        Returns:
            Dict[str, Any]: Created game document
        """
        game = {"chat_id": chat_id, "message_id": message_id, "scenario": scenario, "initiator_id": initiator_id, "start_time": datetime.utcnow(), "end_time": end_time, "status": "active", "players": []}

        result = await self.games.insert_one(game)
        game["_id"] = result.inserted_id
        return game

    async def get_active_game(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the active game for a chat if it exists.

        Args:
            chat_id: Chat ID to check for active game

        Returns:
            Optional[Dict[str, Any]]: Active game document if found, None otherwise
        """
        log.info("Checking for active game", chat_id=chat_id)
        game = await self.games.find_one({"chat_id": chat_id, "status": "active"})
        log.info("Active game query result", game=game)
        return game

    async def get_random_scenario(self) -> Optional[Dict[str, Any]]:
        """
        Get a random scenario from the scenarios collection.

        Returns:
            Optional[Dict[str, Any]]: Random scenario document if found, None otherwise
        """
        log.info("Getting random scenario")
        pipeline = [{"$sample": {"size": 1}}]
        scenarios = []
        async for scenario in self.scenarios.aggregate(pipeline):
            scenarios.append(scenario)

        if not scenarios:
            log.error("No scenarios found in database")
            return None

        log.info("Got random scenario", scenario=scenarios[0])
        return scenarios[0]

    async def add_player_strategy(self, game_id: ObjectId, user_id: int, username: str, strategy: str) -> bool:
        """
        Add a player's strategy to the game.

        Args:
            game_id: ID of the game
            user_id: User submitting the strategy
            username: Username of the player
            strategy: The survival strategy text

        Returns:
            bool: True if strategy was added, False otherwise
        """
        result = await self.games.update_one(
            {
                "_id": game_id,
                "status": "active",
                "players.user_id": {"$ne": user_id},  # Ensure user hasn't already submitted
            },
            {"$push": {"players": {"user_id": user_id, "mention": username, "strategy": strategy, "evaluation": None}}},
        )
        return result.modified_count > 0

    async def update_game_status(self, game_id: ObjectId, status: str) -> bool:
        """
        Update the game status.

        Args:
            game_id: ID of the game to update
            status: New status value

        Returns:
            bool: True if update was successful, False otherwise
        """
        update_data = {"status": status, "end_time": datetime.utcnow() if status == "finished" else None}

        result = await self.games.update_one({"_id": game_id}, {"$set": update_data})
        return result.modified_count > 0

    async def update_player_evaluation(self, game_id: ObjectId, user_id: int, evaluation: Dict[str, str]) -> bool:
        """
        Update a player's strategy evaluation.

        Args:
            game_id: ID of the game
            user_id: User whose strategy is being evaluated
            evaluation: Evaluation result containing decision and details

        Returns:
            bool: True if update was successful, False otherwise
        """
        result = await self.games.update_one({"_id": game_id, "players.user_id": user_id}, {"$set": {"players.$.evaluation": evaluation}})
        return result.modified_count > 0

    async def get_game_by_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a game by its announcement message ID.

        Args:
            message_id: ID of the game announcement message

        Returns:
            Optional[Dict[str, Any]]: Game document if found, None otherwise
        """
        return await self.games.find_one({"message_id": message_id})

    async def get_user_games(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get games initiated by a specific user.

        Args:
            user_id: User ID to fetch games for
            limit: Maximum number of games to return

        Returns:
            List[Dict[str, Any]]: List of game documents
        """
        cursor = self.games.find({"initiator_id": user_id}).sort("start_time", -1).limit(limit)
        return await cursor.to_list(length=None)

    async def get_chat_games(self, chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get games played in a specific chat.

        Args:
            chat_id: Chat ID to fetch games for
            limit: Maximum number of games to return

        Returns:
            List[Dict[str, Any]]: List of game documents
        """
        cursor = self.games.find({"chat_id": chat_id}).sort("start_time", -1).limit(limit)
        return await cursor.to_list(length=None)
