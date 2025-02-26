import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pyrogram.enums import ParseMode
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository
from src.database.repository.message_repository import MessageRepository
from src.database.repository.peer_config_repository import PeerConfigRepository
from src.services.openrouter import OpenRouter
from .models import SummarizationResponse

_summary_job = None
log = get_logger(__name__)

# Constants
MOSCOW_TZ = pytz.timezone("Europe/Moscow")
# MIN_MESSAGES_THRESHOLD is now loaded from config
DEBUG = False  # Feature toggle for debug mode
DEBUG_CHAT_ID = -1001716442415  # Debug chat ID
MESSAGE_TYPES = {
    "text": lambda m: m.get("text", ""),
    "photo": lambda m: f"[ФОТО] {m.get('caption', '')}",
    "sticker": lambda m: "[СТИКЕР]",
    "video_note": lambda m: "[ВИДЕОКРУГ]",
    "voice": lambda m: "[ГОЛОСОВОЕ]",
}


class InsufficientDataError(Exception):
    """Raised when there are not enough messages to generate a summary"""
    pass


async def init_summary(message_repository: MessageRepository, config_repository: PeerConfigRepository, client=None):
    """Initialize the summary job singleton."""
    global _summary_job
    if _summary_job is None:
        _summary_job = SummaryJob(message_repository, config_repository, client)
        # Initialize configuration
        await _summary_job.initialize_config()
    elif client and not _summary_job.client:
        _summary_job.client = client
    return _summary_job


class SummaryJob:
    def __init__(self, message_repository, config_repository, client=None):
        self.message_repository = message_repository
        self.config_repository = config_repository
        self.scheduler = AsyncIOScheduler()
        self.openrouter = OpenRouter()
        self.client = client

        # Get database client for config repository
        db_client = DatabaseClient.get_instance()
        self.config_repo = BotConfigRepository(db_client)

        # These will be loaded from config in async init
        self.system_prompt = ""
        self.model_name = "openai/gpt-4o-mini"  # Default
        self.min_messages_threshold = 60  # Default

        # Set logs directory based on environment
        self.logs_dir = "/app/logs/chat_summaries" if os.getenv("DOCKER_ENV") else "logs/chat_summaries"
        log.info("Initializing summary job", logs_dir=self.logs_dir)

        # Create logs directory if it doesn't exist
        os.makedirs(self.logs_dir, exist_ok=True)

        # Load configurations asynchronously in initialize method

        # Get cron schedule from env or use default (10:00 MSK daily)
        cron_schedule = os.getenv('SUMMARIZATION_CRON', '0 10 * * *')
        log.info("Configuring schedule", cron_schedule=cron_schedule)

        # Schedule job using cron expression
        # Note: client will be passed when the job is triggered
        self.scheduler.add_job(
            self.generate_daily_summary,
            CronTrigger.from_crontab(
                cron_schedule,
                timezone=MOSCOW_TZ
            ),
            misfire_grace_time=3600  # Allow job to run up to 1 hour late
        )

        self.scheduler.start()
        log.info("Summary job scheduler started")

    async def initialize_config(self):
        """Load configuration from bot_config_repository"""
        try:
            # Get summary plugin configuration
            config = await self.config_repo.get_plugin_config("summary")

            # Load system prompt
            self.system_prompt = config.get("SUMMARY_SYSTEM_PROMPT", "")

            # Load model name
            self.model_name = config.get("SUMMARY_MODEL_NAME")

            # Load min messages threshold
            self.min_messages_threshold = config.get("SUMMARY_MIN_MESSAGES_THRESHOLD", 60)

            log.info("Summary plugin configuration loaded",
                     model=self.model_name,
                     threshold=self.min_messages_threshold)

        except Exception as e:
            log.error("Error loading summary configuration", error=str(e))

    async def _generate_summary(self, chat_log: str) -> Optional[Dict]:
        """Generate a summary of the chat log using OpenRouter API"""
        try:
            # Use beta.chat.completions.parse with the Pydantic model
            completion = await self.openrouter.client.beta.chat.completions.parse(
                messages=[
                    {
                        "role": "system",
                        "content": self.system_prompt,
                    },
                    {"role": "user", "content": chat_log},
                ],
                model=self.model_name,
                temperature=1,
                max_tokens=1000,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                response_format=SummarizationResponse
            )

            log.info("Received summary response", response=completion)

            # The response is already parsed into SummarizationResponse model
            summary = completion.choices[0].message.parsed

            log.info("Summary generated successfully", themes_count=len(summary.themes))

            return summary

        except Exception as e:
            log.error("Error generating summary", error=str(e))
            return None

    def _format_message(self, message: Dict) -> Optional[str]:
        """Format a message according to the specified format."""
        try:
            # Get message metadata
            msg_id = message.get("id", "")
            created_at = message.get("created_at")
            if not created_at:
                return None

            # Convert UTC to Moscow time
            local_time = created_at.astimezone(MOSCOW_TZ)
            time_str = local_time.strftime('%H:%M:%S')

            # Get user info
            user = message.get("from_user", {})
            name = user.get("first_name", "Unknown")
            if last_name := user.get("last_name"):
                name += f" {last_name}"
            if username := user.get("username"):
                name += f" (@{username})"

            # Get message content
            content = ""
            for msg_type, content_func in MESSAGE_TYPES.items():
                if msg_type in message:
                    content = content_func(message)
                    break

            if not content and "text" in message:
                content = message["text"]

            if not content:
                return None

            # Check for reposts and forwards
            repost_tag = ""
            if "forwards" in message or "views" in message:
                repost_tag = "[ПОСТ ИЗ КАНАЛА] "
            elif "forward_from_message_id" in message:
                repost_tag = "[ПЕРЕСЛАННОЕ СООБЩЕНИЕ] "

            # Replace actual newlines with \n literal
            content = content.replace("\n", "\\n")

            # Add repost tag to the beginning of the content
            if repost_tag:
                content = f"{repost_tag}{content}"

            return f"[{time_str}] [{msg_id}] {name}: {content}"

        except Exception as e:
            log.error("Error formatting message", error=str(e))
            return None

    async def get_messages_for_date(self, chat_id: int, date: datetime) -> List[Dict]:
        """Get messages for a specific chat and date in Moscow timezone."""
        try:
            date_str = date.strftime('%Y-%m-%d')

            # Convert date to start and end of day in MSK
            start_date = MOSCOW_TZ.localize(
                datetime.combine(date.date(), datetime.min.time())
            )
            end_date = start_date + timedelta(days=1)

            # Convert to UTC for MongoDB query
            start_date_utc = start_date.astimezone(pytz.UTC)
            end_date_utc = end_date.astimezone(pytz.UTC)

            # Query messages within the date range for specific chat
            cursor = self.message_repository.collection.find({
                "created_at": {
                    "$gte": start_date_utc,
                    "$lt": end_date_utc
                },
                "chat.id": chat_id,
                "$and": [
                    {"$or": [
                        {"text": {"$exists": True, "$ne": "", "$not": {"$regex": "^/"}}},
                        # Non-empty text that doesn't start with /
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

        except Exception as e:
            log.error("Error fetching messages", error=str(e))
            return []

    async def generate_chat_summary(self, chat_id: int, chat_title: str, date: datetime, is_forced: bool = False):
        """Generate summary for a specific chat."""
        try:
            date_str = date.strftime('%Y-%m-%d')

            messages = await self.get_messages_for_date(chat_id, date)

            if len(messages) < self.min_messages_threshold:
                if is_forced:
                    raise InsufficientDataError(
                        f"Insufficient messages: {len(messages)} messages"
                    )
                log.debug("Skipping summary: not enough messages",
                          chat_id=chat_id,
                          chat_title=chat_title,
                          message_count=len(messages),
                          threshold=self.min_messages_threshold)
                return

            log.info("Generating summary",
                     chat_id=chat_id,
                     chat_title=chat_title,
                     date=date_str,
                     message_count=len(messages))

            log.debug("Processing messages",
                      chat_id=chat_id,
                      message_count=len(messages))

            # Format messages
            formatted_lines = []
            for message in messages:
                if formatted_msg := self._format_message(message):
                    formatted_lines.append(formatted_msg)

            if not formatted_lines:
                log.info("No valid messages to summarize",
                         chat_id=chat_id,
                         chat_title=chat_title)
                return

            log.info("Messages processed",
                     chat_id=chat_id,
                     original_count=len(messages),
                     final_count=len(formatted_lines))

            # Get human readable date
            human_date = date.strftime('%B %d, %Y')  # e.g. February 23, 2025

            # Generate summary using OpenRouter
            # Prepare chat log - same format as written to file
            chat_log = f"Chat: {chat_title} [{chat_id}]\n"
            chat_log += f"Date: {date_str} ({human_date})\n"
            chat_log += "-" * 50 + "\n\n"
            chat_log += '\n'.join(formatted_lines)

            summary = await self._generate_summary(chat_log)

            if not summary or not summary.themes:
                log.error("Invalid summarization result",
                          chat_id=chat_id,
                          chat_title=chat_title)
                return

            # Write to file
            chat_dir = os.path.join(self.logs_dir, str(chat_id))
            os.makedirs(chat_dir, exist_ok=True)

            filename = os.path.join(chat_dir, f"chat_log_{date_str}.txt")
            summary_filename = os.path.join(chat_dir, f"summary_{date_str}.json")

            log.debug("Writing summary to files",
                      chat_id=chat_id,
                      log_filename=filename,
                      summary_filename=summary_filename)

            # Write chat log - exactly the same format as sent to OpenRouter
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(chat_log)

            # Write summary if available - use model's json() method
            with open(summary_filename, 'w', encoding='utf-8') as f:
                json_str = summary.model_dump_json(indent=2)
                f.write(json_str)

            log.info("Summary files written successfully",
                     chat_id=chat_id,
                     chat_title=chat_title,
                     log_filename=filename,
                     summary_filename=summary_filename)

            # Format and return summary text
            message_text = "📊 Итоги обсуждений за "
            message_text += "сегодня" if date.date() == datetime.now(MOSCOW_TZ).date() else "вчера"
            message_text += ":\n\n"

            for theme in summary.themes:
                message_text += f"{theme.emoji} **{theme.name}** "

                if theme.messages_id:
                    links = [
                        f"[{i + 1}](t.me/c/{str(chat_id)[4:]}/{msg_id})"
                        for i, msg_id in enumerate(theme.messages_id)
                    ]
                    message_text += f"({', '.join(links)})\n"
                else:
                    message_text += "\n"

                for point in theme.key_takeaways:
                    message_text += f"• {point}\n"
                message_text += "\n"

            return message_text

        except InsufficientDataError:
            raise
        except Exception as e:
            log.error("Error generating chat summary",
                      error=str(e),
                      chat_id=chat_id,
                      date=date.strftime('%Y-%m-%d'))

    async def generate_daily_summary(self, client=None):
        """Generate daily summary of messages for all enabled chats."""
        # Use the stored client if none is provided
        client = client or self.client
        try:
            # Get yesterday's date in Moscow timezone
            yesterday = datetime.now(MOSCOW_TZ) - timedelta(days=1)
            date_str = yesterday.strftime('%Y-%m-%d')

            log.info("Starting daily summary generation", date=date_str)

            # Determine which chats to process based on DEBUG setting
            if DEBUG:
                # Only process the specific debug chat ID in debug mode
                chat_ids = [DEBUG_CHAT_ID]
                log.info("Processing debug chat only (DEBUG=True)", chat_id=DEBUG_CHAT_ID)
            else:
                # Get all non-private chats in normal mode
                # First get all distinct chat documents with their type
                pipeline = [
                    {"$match": {"chat.type": {"$ne": "ChatType.PRIVATE"}}},  # Exclude private chats
                    {"$group": {"_id": "$chat.id"}}
                ]
                cursor = self.message_repository.collection.aggregate(pipeline)
                result = await cursor.to_list(length=None)
                chat_ids = [doc["_id"] for doc in result]
                log.info("Processing all non-private chats (DEBUG=False)", chat_count=len(chat_ids))

            processed_count = 0
            enabled_count = 0

            for chat_id in chat_ids:
                try:
                    # Check if summarization is enabled for this chat using the framework
                    from src.config.framework import get_chat_setting
                    
                    if not await get_chat_setting(chat_id, "summary", default=False):
                        log.debug("Summary disabled for chat", chat_id=chat_id)
                        continue

                    enabled_count += 1

                    # Get chat title from any message
                    chat_msg = await self.message_repository.collection.find_one({"chat.id": chat_id})
                    chat_title = chat_msg["chat"].get("title", str(chat_id)) if chat_msg else str(chat_id)

                    # Generate summary for this chat
                    summary_text = await self.generate_chat_summary(chat_id, chat_title, yesterday)
                    if summary_text and client:
                        processed_count += 1
                        # Send the summary_text to the chat
                        try:
                            await client.send_message(
                                chat_id=chat_id,
                                text=summary_text,
                                disable_web_page_preview=True,
                                parse_mode=ParseMode.MARKDOWN
                            )
                            log.info("Summary sent to chat", chat_id=chat_id, chat_title=chat_title)
                        except Exception as e:
                            log.error("Failed to send summary to chat",
                                      error=str(e),
                                      chat_id=chat_id)

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
