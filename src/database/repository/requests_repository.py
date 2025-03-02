"""Repository for requests to various APIs plugin."""

from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from bson.objectid import ObjectId

from structlog import get_logger

from src.database.client import DatabaseClient

log = get_logger(__name__)

class RequestRepository:
    """Repository for handling request history."""

    def __init__(self):
        """Initialize the repository with database client."""
        self.db_client = DatabaseClient.get_instance()
        self.db = self.db_client.db
        self.requests_collection = self.db["requests"]

    async def initialize(self):
        """Initialize the repository by creating indexes."""
        try:
            # Create index on timestamp for fast retrieval by date
            await self.requests_collection.create_index("timestamp")
            # Create index on user_id for fast retrieval by user
            await self.requests_collection.create_index("user_id")
            # Create index on chat_id for fast retrieval by chat
            await self.requests_collection.create_index("chat_id")

            log.info("RequestRepository initialized successfully")
        except Exception as e:
            log.error("Error initializing RequestRepository", error=str(e))

    async def _execute_db_operation(self, operation_name: str, operation, **log_params) -> Any:
        """
        Execute a database operation with standardized error handling.
        
        Args:
            operation_name: Name of the operation for logging
            operation: Async function to execute
            **log_params: Additional parameters to include in log messages
            
        Returns:
            Result of the operation or None/[] if an error occurred
        """
        try:
            result = await operation()
            return result
        except Exception as e:
            log.error(f"Error in {operation_name}", error=str(e), **log_params)
            # Return appropriate default value based on operation type
            if operation_name.startswith("get"):
                return []
            return None

    async def create_request(self, req_type: str, user_id: int, chat_id: int, prompt: str, config: Dict[str, Any],
                           payload: Dict[str, Any], status: str = "processing") -> Dict[str, Any]:
        """
        Create a new request record.

        Args:
            req_type: The type of request (e.g., "imagegen")
            user_id: The ID of the user who made the request
            chat_id: The ID of the chat where the request was made
            prompt: The original prompt text
            config: The user's configuration used for the request
            payload: The full payload sent to the API
            status: Initial status of the request (default: "processing")

        Returns:
            The created request document
        """
        async def _create():
            request = {
                "type": req_type,
                "user_id": user_id,
                "chat_id": chat_id,
                "timestamp": datetime.utcnow(),
                "prompt": prompt,
                "config": config,
                "payload": payload,
                "image_urls": [],
                "status": status,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
                    
            # Insert the request record
            result = await self.requests_collection.insert_one(request)
            request["_id"] = result.inserted_id
            
            log.info("Created new request", user_id=user_id, prompt=prompt, status=status)
            return request
            
        return await self._execute_db_operation(
            "create_request",
            _create,
            user_id=user_id,
            prompt=prompt
        )
            
    async def update_request(self, request_id: str, image_urls: List[str] = None,
                           error: str = None, status: str = None) -> Dict[str, Any]:
        """
        Update an existing image generation request.

        Args:
            request_id: The ID of the request to update
            image_urls: The URLs of the generated images (if successful)
            error: Error message if request failed
            status: New status of the request (success, failure)

        Returns:
            The updated request document or None if not found
        """
        async def _update():
            # Prepare update data
            update_data = {"updated_at": datetime.utcnow()}
            
            if image_urls is not None:
                update_data["image_urls"] = image_urls
                
            if error is not None:
                update_data["error"] = error
                
            if status is not None:
                update_data["status"] = status
            
            # Update the request
            result = await self.requests_collection.update_one(
                {"_id": ObjectId(request_id)},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                log.warning("Request not found for update", request_id=request_id)
                return None
                
            # Get the updated document
            updated_request = await self.requests_collection.find_one({"_id": ObjectId(request_id)})
            
            log.info("Updated request", request_id=request_id, status=status)
            return updated_request
            
        return await self._execute_db_operation(
            "update_request",
            _update,
            request_id=request_id
        )
            
    # Keeping the old method name for backward compatibility, but with updated implementation
    async def save_request(self, req_type: str, user_id: int, chat_id: int, prompt: str, config: Dict[str, Any],
                          payload: Dict[str, Any], image_urls: List[str] = None,
                          error: str = None, status: str = "processing") -> Dict[str, Any]:
        """
        Save a record of an image generation request.
        If this is a new request, creates a new document.
        If this is an update to an existing request, updates the document.

        Args:
            req_type: The type of request (e.g., "imagegen")
            user_id: The ID of the user who made the request
            chat_id: The ID of the chat where the request was made
            prompt: The original prompt text
            config: The user's configuration used for the request
            payload: The full payload sent to the API
            image_urls: The URLs of the generated images (if successful)
            error: Error message if request failed
            status: Status of the request (processing, success, failure)

        Returns:
            The saved request document
        """
        async def _save():
            # Check if this is a new request or an update to an existing one
            if status == "processing" or not image_urls:
                # This is a new request
                return await self.create_request(req_type, user_id, chat_id, prompt, config, payload, status)
            else:
                # This is an update to an existing request
                # Find the most recent processing request for this user/chat/prompt
                cursor = self.requests_collection.find({
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "prompt": prompt,
                    "status": "processing"
                }).sort("created_at", -1).limit(1)
                
                existing_requests = await cursor.to_list(length=1)
                
                if existing_requests:
                    # Update the existing request
                    existing_request = existing_requests[0]
                    return await self.update_request(
                        str(existing_request["_id"]),
                        image_urls=image_urls,
                        error=error,
                        status=status
                    )
                else:
                    # No existing request found, create a new one
                    return await self.create_request(req_type, user_id, chat_id, prompt, config, payload, status)
                    
        return await self._execute_db_operation(
            "save_request",
            _save,
            user_id=user_id,
            prompt=prompt
        )

    async def _get_requests(self, query: Dict[str, Any], limit: int, log_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generic method to get requests based on a query.
        
        Args:
            query: MongoDB query to filter requests
            limit: Maximum number of requests to return
            log_context: Context information for logging
            
        Returns:
            List of request documents
        """
        async def _get():
            cursor = self.requests_collection.find(query).sort("timestamp", -1).limit(limit)
            return await cursor.to_list(length=limit)
            
        return await self._execute_db_operation("get_requests", _get, **log_context)

    async def get_user_requests(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent image generation requests for a user.

        Args:
            user_id: The ID of the user
            limit: Maximum number of requests to return

        Returns:
            List of request documents
        """
        return await self._get_requests(
            query={"user_id": user_id},
            limit=limit,
            log_context={"user_id": user_id}
        )

    async def get_chat_requests(self, chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent image generation requests for a chat.

        Args:
            chat_id: The ID of the chat
            limit: Maximum number of requests to return

        Returns:
            List of request documents
        """
        return await self._get_requests(
            query={"chat_id": chat_id},
            limit=limit,
            log_context={"chat_id": chat_id}
        )

    async def get_recent_requests(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent image generation requests across all users.

        Args:
            limit: Maximum number of requests to return

        Returns:
            List of request documents
        """
        return await self._get_requests(
            query={},
            limit=limit,
            log_context={}
        )