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

# Environment settings
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 1000))
SENTIMENT_MODEL = os.getenv('SENTIMENT_MODEL', 'seara/rubert-tiny2-russian-sentiment')
SENSITIVE_MODEL = os.getenv('SENSITIVE_TOPICS_MODEL', 'Skoltech/russian-sensitive-topics')
MONGODB_URI = f"mongodb://{os.getenv('MONGODB_USERNAME')}:{os.getenv('MONGODB_PASSWORD')}@{os.getenv('MONGODB_HOST')}:{os.getenv('MONGODB_PORT')}"

current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(LOGS_DIR, f'sentiment_analysis_{current_time}.log')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file),
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
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")
        
        # Initialize sentiment model
        logger.info("Loading sentiment model...")
        self.sentiment_model = pipeline(
            task="text-classification",
            model=SENTIMENT_MODEL,
            device=self.device,
            batch_size=32,
            model_kwargs={"cache_dir": CACHE_DIR}
        )
        
        
        logger.info("Loading sensitive topics model...")
        self.topics_tokenizer = BertTokenizer.from_pretrained(
            SENSITIVE_MODEL,
            cache_dir=CACHE_DIR
        )
        self.topics_model = BertForSequenceClassification.from_pretrained(
            SENSITIVE_MODEL,
            cache_dir=CACHE_DIR
        ).to(self.device)
        self.topics_model.eval()
        
        # Load topic dictionary
        topic_file = Path("id2topic.json")
        if not topic_file.exists():
            raise FileNotFoundError("id2topic.json not found")
        with topic_file.open() as f:
            self.topic_dict = json.load(f)
            
    @torch.no_grad()
    def analyze_sentiment(self, texts: List[str]) -> List[Dict[str, float]]:
        """Analyze sentiment for a batch of texts."""
        results = self.sentiment_model(texts, top_k=None)
        return [
            {item["label"].lower(): item["score"] for item in batch_result}
            for batch_result in results
        ]
    
    @torch.no_grad()
    def analyze_topics(self, texts: List[str], threshold: float = 0.1) -> List[Dict[str, float]]:
        """Analyze sensitive topics for a batch of texts."""
        encoded = self.topics_tokenizer.batch_encode_plus(
            texts,
            max_length=512,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
            return_token_type_ids=False
        ).to(self.device)
        
        outputs = self.topics_model(**encoded)
        probabilities = F.softmax(outputs.logits, dim=-1).cpu().numpy()
        
        return [
            {
                self.topic_dict[str(idx)].lower(): float(prob)
                for idx, prob in enumerate(probs)
                if float(prob) >= threshold
            }
            for probs in probabilities
        ]

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
    texts = [msg["message_content"] for msg in batch]
    
    logger.info(f"Running sentiment analysis on batch of {len(texts)} texts...")
    sentiments = models.analyze_sentiment(texts)
    
    logger.info(f"Running topic analysis on batch of {len(texts)} texts...")
    topics = models.analyze_topics(texts)
    
    # Combine results
    processed = []
    for msg, sentiment, topic in zip(batch, sentiments, topics):
        sentiment_data = {
            **sentiment,
            "sensitive_topics": topic
        }
        processed.append({
            "_id": msg["_id"],
            "sentiment": sentiment_data
        })
    
    return processed

async def update_messages(db: AsyncIOMotorDatabase, messages: List[Dict]):
    """Update messages with analysis results."""
    if not messages:
        return
        
    collection = db["messages"]
    operations = [
        UpdateOne(
            {"_id": msg["_id"]},
            {"$set": {"sentiment": msg["sentiment"]}},
            upsert=False
        )
        for msg in messages
    ]
    
    # Execute in batches
    total_batches = (len(operations) - 1) // BATCH_SIZE + 1
    for i in tqdm(range(0, len(operations), BATCH_SIZE), total=total_batches, desc="Updating database"):
        batch = operations[i:i + BATCH_SIZE]
        logger.info(f"Writing batch {i//BATCH_SIZE + 1}/{total_batches} to database...")
        await collection.bulk_write(batch, ordered=False)
        logger.info(f"Batch {i//BATCH_SIZE + 1} complete")

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
