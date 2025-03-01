"""Combined sentiment and sensitive topics analysis module."""
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from tqdm import tqdm

import torch
import torch.nn.functional as F
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import UpdateOne
from transformers import pipeline, BertForSequenceClassification, BertTokenizer

import os
import logging
import logging.handlers
from datetime import datetime

# Define cache and logs directories
CACHE_DIR = os.getenv('MODELS_CACHE_DIR', '/app/cache')
LOGS_DIR = os.getenv('LOGS_DIR', '/app/logs')

# Set all possible HuggingFace cache-related environment variables
os.environ['TRANSFORMERS_CACHE'] = CACHE_DIR
os.environ['HF_HOME'] = CACHE_DIR
os.environ['HF_DATASETS_CACHE'] = CACHE_DIR
os.environ['HUGGINGFACE_HUB_CACHE'] = CACHE_DIR
os.environ['XDG_CACHE_HOME'] = CACHE_DIR


# Create directories if they don't exist
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)

# Environment peer_config
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 100))  # Reduced from 1000 to prevent memory pressure
SENTIMENT_MODEL = os.getenv('SENTIMENT_MODEL', 'seara/rubert-tiny2-russian-sentiment')
SENSITIVE_MODEL = os.getenv('SENSITIVE_TOPICS_MODEL', 'Skoltech/russian-sensitive-topics')
from urllib.parse import quote_plus

# Use mongodb service name when running in docker, otherwise use MONGO_BIND_IP
mongodb_host = "mongodb" if os.getenv('DOCKER_ENV') == 'true' else os.getenv('MONGO_BIND_IP')
MONGODB_URI = f"mongodb://{quote_plus(os.getenv('MONGO_USERNAME'))}:{quote_plus(os.getenv('MONGO_PASSWORD'))}@{mongodb_host}:{os.getenv('MONGO_PORT')}"

# Log file configuration with rotation
log_file = os.path.join(LOGS_DIR, 'sentiment_analysis.log')

# Configure logging with rotation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        # Rotate log files daily, keep 7 days of logs, compress old logs
        logging.handlers.TimedRotatingFileHandler(
            filename=log_file,
            when='midnight',  # Rotate at midnight
            interval=1,       # Daily rotation
            backupCount=7,    # Keep 7 days of logs
            encoding='utf-8',
            delay=False,
            utc=False,
            atTime=None
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Set HuggingFace hub options
os.environ['CURL_CA_BUNDLE'] = '/etc/ssl/certs/ca-certificates.crt'
os.environ['REQUESTS_CA_BUNDLE'] = '/etc/ssl/certs/ca-certificates.crt'
os.environ['SSL_CERT_FILE'] = '/etc/ssl/certs/ca-certificates.crt'

class AnalysisModels:
    def __init__(self):
        # Log system information
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")
        if torch.cuda.is_available():
            logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
            logger.info(f"Available GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB")
        
        # Initialize sentiment model with detailed logging
        logger.info(f"Loading sentiment model: {SENTIMENT_MODEL}")
        start_time = datetime.now()
        self.sentiment_model = pipeline(
            task="text-classification",
            model=SENTIMENT_MODEL,
            device=self.device,
            batch_size=32,
            model_kwargs={"cache_dir": CACHE_DIR}
        )
        logger.info(f"Sentiment model loaded in {(datetime.now() - start_time).total_seconds():.2f} seconds")
        logger.info(f"Sentiment model configuration: {self.sentiment_model.model.config}")
        
        # Initialize topics model with detailed logging
        logger.info(f"Loading sensitive topics model: {SENSITIVE_MODEL}")
        start_time = datetime.now()
        self.topics_tokenizer = BertTokenizer.from_pretrained(
            SENSITIVE_MODEL,
            cache_dir=CACHE_DIR
        )
        self.topics_model = BertForSequenceClassification.from_pretrained(
            SENSITIVE_MODEL,
            cache_dir=CACHE_DIR
        ).to(self.device)
        self.topics_model.eval()
        
        # Load topic dictionary from the same directory as this script
        topic_file = Path(__file__).parent / "id2topic.json"
        if not topic_file.exists():
            raise FileNotFoundError("id2topic.json not found")
        with topic_file.open() as f:
            self.topic_dict = json.load(f)
            
    @torch.no_grad()
    def analyze_sentiment(self, texts: List[str]) -> List[Dict[str, float]]:
        """Analyze sentiment for a batch of texts."""
        start_time = datetime.now()
        logger.info(f"Starting sentiment analysis for {len(texts)} texts")
        
        try:
            results = self.sentiment_model(texts, top_k=None)
            process_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Sentiment analysis completed in {process_time:.2f} seconds")
            
            if torch.cuda.is_available():
                memory_allocated = torch.cuda.memory_allocated() / 1024**2
                logger.info(f"GPU memory allocated: {memory_allocated:.2f} MB")
            
            return [
                {item["label"].lower(): item["score"] for item in batch_result}
                for batch_result in results
            ]
        except Exception as e:
            logger.error(f"Error during sentiment analysis: {str(e)}", exc_info=True)
            raise
    
    @torch.no_grad()
    def analyze_topics(self, texts: List[str], threshold: float = 0.1) -> List[Dict[str, float]]:
        """Analyze sensitive topics for a batch of texts."""
        start_time = datetime.now()
        logger.info(f"Starting topic analysis for {len(texts)} texts with threshold {threshold}")
        
        # Process in smaller sub-batches to reduce memory usage
        SUB_BATCH_SIZE = 32
        results = []
        total_sub_batches = (len(texts) - 1) // SUB_BATCH_SIZE + 1
        
        try:
            for i in range(0, len(texts), SUB_BATCH_SIZE):
                sub_batch = texts[i:i + SUB_BATCH_SIZE]
                batch_start_time = datetime.now()
                logger.info(f"Processing sub-batch {i//SUB_BATCH_SIZE + 1}/{total_sub_batches} ({len(sub_batch)} texts)")
                
                # Use dynamic padding instead of max_length
                encoded = self.topics_tokenizer.batch_encode_plus(
                    sub_batch,
                    max_length=256,  # Reduced from 512
                    padding=True,    # Dynamic padding
                    truncation=True,
                    return_tensors="pt",
                    return_token_type_ids=False
                ).to(self.device)
                
                logger.debug(f"Input shape: {encoded['input_ids'].shape}")
                
                outputs = self.topics_model(**encoded)
                probabilities = F.softmax(outputs.logits, dim=-1).cpu().numpy()
                
                batch_results = [
                    {
                        self.topic_dict[str(idx)].lower(): float(prob)
                        for idx, prob in enumerate(probs)
                        if float(prob) >= threshold
                    }
                    for probs in probabilities
                ]
                results.extend(batch_results)
                
                batch_time = (datetime.now() - batch_start_time).total_seconds()
                logger.info(f"Sub-batch {i//SUB_BATCH_SIZE + 1} completed in {batch_time:.2f} seconds")
                
                if torch.cuda.is_available():
                    memory_allocated = torch.cuda.memory_allocated() / 1024**2
                    logger.info(f"GPU memory allocated: {memory_allocated:.2f} MB")
                    torch.cuda.empty_cache()
                    logger.debug("CUDA cache cleared")
            
            total_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Topic analysis completed in {total_time:.2f} seconds")
            return results
            
        except Exception as e:
            logger.error(f"Error during topic analysis: {str(e)}", exc_info=True)
            raise

class DatabaseClient:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        
    async def connect(self) -> AsyncIOMotorDatabase:
        """Connect to MongoDB."""
        self.client = AsyncIOMotorClient(
            MONGODB_URI,
            maxPoolSize=int(os.getenv('MONGODB_POOL_SIZE', 100))
        )
        self.db = self.client[os.getenv('MONGODB_DATABASE')]
        return self.db
        
    async def close(self):
        """Close database connection."""
        if self.client:
            self.client.close()
            await asyncio.sleep(0)
            
    async def get_unprocessed_messages(self) -> List[Dict]:
        """Get messages that need analysis."""
        collection = self.db["messages"]
        
        pipeline = [
            {
                "$match": {
                    "$and": [
                        {"$or": [
                            {"text": {"$exists": True, "$ne": ""}},
                            {"caption": {"$exists": True, "$ne": ""}}
                        ]},
                        {"$or": [
                            {"event_type": "Message"},
                            {"_": "Message"}
                        ]},
                        {"$or": [
                            {"from_user.is_bot": {"$exists": False}},
                            {"from_user.is_bot": False}
                        ]},
                        {"$or": [
                            {"sentiment": {"$exists": False}},
                            {"sentiment.positive": {"$exists": False}},
                            {"sentiment.sensitive_topics": {"$exists": False}}
                        ]}
                    ]
                }
            },
            {
                "$addFields": {
                    "message_content": {"$ifNull": ["$text", "$caption"]}
                }
            },
            {
                "$match": {
                    "message_content": {"$not": {"$regex": "^/"}}
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "message_content": 1
                }
            }
        ]
        
        cursor = collection.aggregate(pipeline, allowDiskUse=True)
        return await cursor.to_list(length=None)

async def process_batch(models: AnalysisModels, batch: List[Dict]) -> List[Dict]:
    """Process a batch of messages with both sentiment and topic analysis."""
    batch_start_time = datetime.now()
    texts = [msg["message_content"] for msg in batch]
    
    # Log batch statistics
    avg_length = sum(len(text) for text in texts) / len(texts)
    max_length = max(len(text) for text in texts)
    logger.info(f"Processing batch of {len(texts)} texts:")
    logger.info(f"- Average text length: {avg_length:.1f} characters")
    logger.info(f"- Maximum text length: {max_length} characters")
    
    try:
        # Sentiment Analysis with timing
        logger.info("Starting sentiment analysis...")
        sentiment_start = datetime.now()
        sentiments = models.analyze_sentiment(texts)
        sentiment_time = (datetime.now() - sentiment_start).total_seconds()
        logger.info(f"Sentiment analysis completed in {sentiment_time:.2f} seconds")
        
        # Topic Analysis with timing
        logger.info("Starting topic analysis...")
        topic_start = datetime.now()
        topics = models.analyze_topics(texts)
        topic_time = (datetime.now() - topic_start).total_seconds()
        logger.info(f"Topic analysis completed in {topic_time:.2f} seconds")
        
        # Combine results with statistics
        processed = []
        total_topics = 0
        for msg, sentiment, topic in zip(batch, sentiments, topics):
            total_topics += len(topic)
            sentiment_data = {
                **sentiment,
                "sensitive_topics": topic
            }
            processed.append({
                "_id": msg["_id"],
                "sentiment": sentiment_data
            })
        
        # Log processing statistics
        total_time = (datetime.now() - batch_start_time).total_seconds()
        logger.info(f"Batch processing statistics:")
        logger.info(f"- Total processing time: {total_time:.2f} seconds")
        logger.info(f"- Sentiment analysis time: {sentiment_time:.2f} seconds")
        logger.info(f"- Topic analysis time: {topic_time:.2f} seconds")
        logger.info(f"- Average topics per message: {total_topics/len(batch):.2f}")
        
        if torch.cuda.is_available():
            memory_allocated = torch.cuda.memory_allocated() / 1024**2
            memory_reserved = torch.cuda.memory_reserved() / 1024**2
            logger.info(f"GPU memory status:")
            logger.info(f"- Allocated: {memory_allocated:.2f} MB")
            logger.info(f"- Reserved: {memory_reserved:.2f} MB")
        
        return processed
        
    except Exception as e:
        logger.error(f"Error during batch processing: {str(e)}", exc_info=True)
        raise

async def update_messages(db: AsyncIOMotorDatabase, messages: List[Dict]):
    """Update messages with analysis results."""
    if not messages:
        logger.info("No messages to update in database")
        return
        
    start_time = datetime.now()
    logger.info(f"Preparing to update {len(messages)} messages in database")
    
    try:
        collection = db["messages"]
        operations = [
            UpdateOne(
                {"_id": msg["_id"]},
                {"$set": {"sentiment": msg["sentiment"]}},
                upsert=False
            )
            for msg in messages
        ]
        
        # Execute in batches with detailed logging
        total_batches = (len(operations) - 1) // BATCH_SIZE + 1
        total_updated = 0
        
        logger.info(f"Starting database updates in {total_batches} batches (batch size: {BATCH_SIZE})")
        
        for i in tqdm(range(0, len(operations), BATCH_SIZE), total=total_batches, desc="Updating database"):
            batch = operations[i:i + BATCH_SIZE]
            batch_start = datetime.now()
            
            logger.info(f"Writing batch {i//BATCH_SIZE + 1}/{total_batches} ({len(batch)} operations)...")
            result = await collection.bulk_write(batch, ordered=False)
            
            # Log batch results
            batch_time = (datetime.now() - batch_start).total_seconds()
            total_updated += result.modified_count
            
            logger.info(f"Batch {i//BATCH_SIZE + 1} completed in {batch_time:.2f} seconds:")
            logger.info(f"- Modified: {result.modified_count}")
            logger.info(f"- Matched: {result.matched_count}")
            if result.upserted_count > 0:
                logger.warning(f"- Unexpected upserts: {result.upserted_count}")
        
        # Log final statistics
        total_time = (datetime.now() - start_time).total_seconds()
        avg_time_per_msg = total_time / len(messages)
        
        logger.info(f"Database update completed in {total_time:.2f} seconds")
        logger.info(f"Update statistics:")
        logger.info(f"- Total messages processed: {len(messages)}")
        logger.info(f"- Total messages updated: {total_updated}")
        logger.info(f"- Average time per message: {avg_time_per_msg*1000:.2f} ms")
        logger.info(f"- Average messages per second: {len(messages)/total_time:.1f}")
        
    except Exception as e:
        logger.error(f"Error during database update: {str(e)}", exc_info=True)
        raise

async def main():
    """Main execution function."""
    logger.info("Starting analysis job")
    start_time = datetime.now()
    
    # Initialize components
    db_client = DatabaseClient()
    try:
        logger.info("Connecting to database...")
        db = await db_client.connect()
        logger.info("Database connection established")
        
        logger.info("Initializing ML models...")
        models = AnalysisModels()
        logger.info("Models initialized successfully")
        
        # Get messages
        logger.info("Fetching unprocessed messages from database...")
        messages = await db_client.get_unprocessed_messages()
        if not messages:
            logger.info("No messages to process")
            return
            
        logger.info(f"Found {len(messages)} messages to process")
        
        # Process in batches
        processed_messages = []
        total_batches = (len(messages) - 1) // BATCH_SIZE + 1
        
        for i in tqdm(range(0, len(messages), BATCH_SIZE), total=total_batches, desc="Processing messages"):
            batch = messages[i:i + BATCH_SIZE]
            logger.info(f"Processing batch {i//BATCH_SIZE + 1}/{total_batches}...")
            batch_results = await process_batch(models, batch)
            processed_messages.extend(batch_results)
            logger.info(f"Batch {i//BATCH_SIZE + 1} processing complete")
        
        # Update database
        logger.info("Starting database updates...")
        await update_messages(db, processed_messages)
        logger.info("Database updates complete")
        
        duration = datetime.now() - start_time
        logger.info(f"Analysis completed in {duration}. Processed {len(messages)} messages.")
        
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("Closing database connection...")
        await db_client.close()
        logger.info("Database connection closed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Process interrupted by user")
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
