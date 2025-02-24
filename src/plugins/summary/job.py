from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from typing import Dict, List
import os
from src.database.message_repository import MessageRepository, PeerRepository
from structlog import get_logger

_summary_job = None
log = get_logger(__name__)


async def init_summary(message_repository: MessageRepository, peer_repository: PeerRepository):
    """Initialize the summary job singleton."""
    global _summary_job
    if _summary_job is None:
        _summary_job = SummaryJob(message_repository, peer_repository)
    return _summary_job

class SummaryJob:
    def __init__(self, message_repository, peer_repository):
        self.message_repository = message_repository
        self.peer_repository = peer_repository
        self.scheduler = AsyncIOScheduler()
        
        # Set logs directory based on environment
        self.logs_dir = "/app/logs/chat_summaries" if os.getenv("DOCKER_ENV") else "logs/chat_summaries"
        log.info("Initializing summary job", logs_dir=self.logs_dir)
        
        # Create logs directory if it doesn't exist
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Get cron schedule from env or use default (10:00 MSK daily)
        cron_schedule = os.getenv('SUMMARIZATION_CRON', '0 10 * * *')
        log.info("Configuring schedule", cron_schedule=cron_schedule)
        
        # Schedule job using cron expression
        self.scheduler.add_job(
            self.generate_daily_summary,
            CronTrigger.from_crontab(
                cron_schedule,
                timezone=pytz.timezone('Europe/Moscow')
            ),
            misfire_grace_time=3600  # Allow job to run up to 1 hour late
        )
        
        self.scheduler.start()
        log.info("Summary job scheduler started")

    def format_message(self, message: Dict) -> str:
        """Format a message according to the specified format."""
        user = message.get("from_user", {})
        first_name = user.get("first_name", "")
        last_name = user.get("last_name", "")
        username = user.get("username", "")
        user_id = user.get("id", "")
        
        # Skip messages without valid user information
        if not (username or user_id or first_name):
            return None
            
        # Use username if available, otherwise use user_id
        identifier = f"@{username}" if username else str(user_id)
        
        # Combine name parts
        name_parts = [first_name] if first_name else []
        if last_name:
            name_parts.append(last_name)
        full_name = " ".join(name_parts) or "Unknown"
        
        # Get message text or caption and replace newlines with \n
        text = message.get("text", "") or message.get("caption", "")
        text = text.replace("\n", "\\n") if text else ""
        
        # Get message timestamp and format it
        created_at = message.get("created_at")
        if created_at:
            # Convert UTC to Moscow time
            msk_tz = pytz.timezone('Europe/Moscow')
            local_time = created_at.astimezone(msk_tz)
            time_str = local_time.strftime('%Y-%m-%d %H:%M:%S MSK')
            return f"[{time_str}] {full_name} [{identifier}]: {text}"
        else:
            return f"{full_name} [{identifier}]: {text}"

    async def get_messages_for_date(self, chat_id: int, date: datetime) -> List[Dict]:
        """Get messages for a specific chat and date in Moscow timezone."""
        msk_tz = pytz.timezone('Europe/Moscow')
        date_str = date.strftime('%Y-%m-%d')
        
        log.debug("Converting date range to MSK", chat_id=chat_id, date=date_str)
        
        # Convert date to start and end of day in MSK
        start_date = msk_tz.localize(
            datetime.combine(date.date(), datetime.min.time())
        )
        end_date = start_date + timedelta(days=1)
        
        # Convert to UTC for MongoDB query
        start_date_utc = start_date.astimezone(pytz.UTC)
        end_date_utc = end_date.astimezone(pytz.UTC)
        
        log.debug("Fetching messages",
                 chat_id=chat_id,
                 date=date_str,
                 start_utc=start_date_utc.isoformat(),
                 end_utc=end_date_utc.isoformat())
        
        # Query messages within the date range for specific chat
        cursor = self.message_repository.collection.find({
            "created_at": {
                "$gte": start_date_utc,
                "$lt": end_date_utc
            },
            "chat.id": chat_id,
            "$and": [
                {"$or": [
                    {"text": {"$exists": True, "$ne": "", "$not": {"$regex": "^/"}}},  # Non-empty text that doesn't start with /
                    {"caption": {"$exists": True, "$ne": ""}}  # Non-empty caption
                ]},
                {"$or": [
                    {"from_user.is_bot": False},  # Include non-bot users
                    {"from_user.is_bot": {"$exists": False}}  # Include users where is_bot field doesn't exist
                ]}
            ]
        }).sort("created_at", 1)  # Sort by date ascending
        
        messages = await cursor.to_list(length=None)
        log.info("Messages fetched",
                chat_id=chat_id,
                date=date_str,
                message_count=len(messages))
        
        return messages

    async def generate_chat_summary(self, chat_id: int, chat_title: str, date: datetime):
        """Generate summary for a specific chat."""
        try:
            date_str = date.strftime('%Y-%m-%d')
            log.info("Starting chat summary generation",
                    chat_id=chat_id,
                    chat_title=chat_title,
                    date=date_str)
            
            messages = await self.get_messages_for_date(chat_id, date)
            
            if not messages:
                log.info("No messages found for chat",
                        chat_id=chat_id,
                        chat_title=chat_title,
                        date=date_str)
                return
            
            log.debug("Processing messages",
                     chat_id=chat_id,
                     message_count=len(messages))
            
            # Format messages and handle duplicates
            formatted_lines = []
            prev_message = None
            duplicate_count = 1
            total_duplicates = 0
            
            for message in messages:
                current_formatted = self.format_message(message)
                
                # Skip invalid messages
                if current_formatted is None:
                    continue
                    
                if prev_message and current_formatted == prev_message:
                    duplicate_count += 1
                else:
                    if prev_message:
                        if duplicate_count > 1:
                            formatted_lines.append(f"{prev_message} (x{duplicate_count})")
                            total_duplicates += duplicate_count - 1
                        else:
                            formatted_lines.append(prev_message)
                    prev_message = current_formatted
                    duplicate_count = 1
            
            # Handle the last message
            if prev_message:
                if duplicate_count > 1:
                    formatted_lines.append(f"{prev_message} (x{duplicate_count})")
                    total_duplicates += duplicate_count - 1
                else:
                    formatted_lines.append(prev_message)
            
            log.info("Messages processed",
                    chat_id=chat_id,
                    original_count=len(messages),
                    duplicate_count=total_duplicates,
                    final_count=len(formatted_lines))
            
            # Write to file
            chat_dir = os.path.join(self.logs_dir, str(chat_id))
            os.makedirs(chat_dir, exist_ok=True)
            
            filename = os.path.join(chat_dir, f"chat_log_{date_str}.txt")
            log.debug("Writing summary to file",
                     chat_id=chat_id,
                     filename=filename)
            
            # Get human readable date
            human_date = date.strftime('%B %d, %Y')  # e.g. February 23, 2025
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Chat: {chat_title} [{chat_id}]\n")
                f.write(f"Date: {date_str} ({human_date})\n")
                f.write("-" * 50 + "\n\n")
                f.write('\n'.join(formatted_lines))
            
            log.info("Summary file written successfully",
                    chat_id=chat_id,
                    chat_title=chat_title,
                    filename=filename)
                
        except Exception as e:
            log.error("Error generating chat summary",
                     error=str(e),
                     chat_id=chat_id,
                     date=date.strftime('%Y-%m-%d'))

    async def generate_daily_summary(self):
        """Generate daily summary of messages for all enabled chats."""
        try:
            # Get yesterday's date in Moscow timezone
            msk_tz = pytz.timezone('Europe/Moscow')
            yesterday = datetime.now(msk_tz) - timedelta(days=1)
            date_str = yesterday.strftime('%Y-%m-%d')
            
            log.info("Starting daily summary generation", date=date_str)
            
            # Get all non-private chats from the database
            cursor = self.message_repository.collection.distinct("chat.id", {
                "chat.type": {"$ne": "ChatType.PRIVATE"}
            })
            chat_ids = await cursor
            
            log.info("Found chats in messages", chat_count=len(chat_ids))
            
            processed_count = 0
            enabled_count = 0
            
            for chat_id in chat_ids:
                try:
                    # Check if summarization is enabled for this chat
                    config = await self.peer_repository.get_peer_config(chat_id)
                    
                    if not config.get("summary_enabled", False):
                        log.debug("Summary disabled for chat", chat_id=chat_id)
                        continue
                    
                    enabled_count += 1
                    
                    # Get chat title from any message
                    chat_msg = await self.message_repository.collection.find_one({"chat.id": chat_id})
                    chat_title = chat_msg["chat"].get("title", str(chat_id)) if chat_msg else str(chat_id)
                    
                    log.info("Generating summary",
                            chat_id=chat_id,
                            chat_title=chat_title,
                            date=date_str)
                    
                    # Generate summary for this chat
                    await self.generate_chat_summary(chat_id, chat_title, yesterday)
                    processed_count += 1
                    
                    log.info("Summary generated successfully",
                            chat_id=chat_id,
                            chat_title=chat_title)
                    
                except Exception as e:
                    log.error("Error processing chat",
                             error=str(e),
                             chat_id=chat_id)
                    continue
            
            log.info("Daily summary generation completed",
                     total_chats=len(chat_ids),
                     enabled_chats=enabled_count,
                     processed_chats=processed_count,
                     date=date_str)
                
        except Exception as e:
            log.error("Error in daily summary generation", error=str(e))