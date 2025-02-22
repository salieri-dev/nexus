import functools
from typing import Optional, Callable, Any
import structlog
from src.database.client import DatabaseClient
from src.security.ratelimiter.repository import RateLimitRepository

logger = structlog.get_logger()


def rate_limit(
    operation: Optional[str] = None,
    window_seconds: int = 10,  # Default 10 second window
    on_rate_limited: Optional[Callable] = None
):
    """
    Rate limiting decorator that uses timestamps to limit operations.
    
    Args:
        operation (Optional[str]): Name of the operation to rate limit. 
            If None, uses the function name.
        window_seconds (int): Time window in seconds. User can only make
            one request per window.
        on_rate_limited (Optional[Callable]): Callback function to execute when rate limit
            is exceeded. Receives the event object as parameter.
    
    Example usage:
        @rate_limit(
            operation="instagram_handler", 
            window_seconds=10,
            on_rate_limited=lambda event: event.reply("You're rate limited!")
        )
        async def handler(client: Client, event: Message):
            # Only one request per 10 seconds per user allowed
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                # Get user_id from Message event
                event = args[1] if len(args) > 1 else None
                if not event or not hasattr(event, 'from_user') or not event.from_user:
                    logger.warning("No user found in message event, skipping rate limit")
                    return await func(*args, **kwargs)
                    
                user_id = event.from_user.id
                op_name = operation or func.__name__

                # Check rate limit
                db_client = DatabaseClient.get_instance()
                rate_limit_repo = RateLimitRepository(db_client)
                
                allowed = await rate_limit_repo.check_rate_limit(
                    user_id=user_id,
                    operation=op_name,
                    window_seconds=window_seconds
                )

                if not allowed:
                    logger.warning(
                        "Rate limit exceeded",
                        user_id=user_id,
                        operation=op_name
                    )
                    # Execute the rate limit callback if provided
                    if on_rate_limited and event:
                        await on_rate_limited(event)
                    return None

                # Execute the function if not rate limited
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    "Error in rate limit decorator",
                    error=str(e),
                    user_id=user_id if 'user_id' in locals() else None,
                    operation=op_name if 'op_name' in locals() else None
                )
                return await func(*args, **kwargs)

        return wrapper
    return decorator