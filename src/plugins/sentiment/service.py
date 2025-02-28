import io
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from scipy.signal import find_peaks
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.message_repository import MessageRepository
from .constants import MIN_MESSAGES, MIN_TEXT_LENGTH, MAX_TEXT_LENGTH, SENTIMENT_THRESHOLD, TOPIC_THRESHOLD, GRAPH_WINDOWS, GRAPH_COLORS, MESSAGES

log = get_logger(__name__)


class SentimentWrapper:
    """Wrapper for sentiment data"""

    def __init__(self, sentiment_dict: Dict[str, Any]):
        self.positive = sentiment_dict.get("positive", 0.0)
        self.negative = sentiment_dict.get("negative", 0.0)
        self.neutral = sentiment_dict.get("neutral", 0.0)
        self.sensitive_topics = sentiment_dict.get("sensitive_topics", {})


class MessageWrapper:
    """Wrapper for message dictionaries to provide expected structure and support both dict and attribute access"""

    def __init__(self, message_dict: Dict[str, Any]):
        # Store the original dictionary
        self._data = message_dict

        # Extract user_id from the message
        if "from_user" in message_dict and "id" in message_dict["from_user"]:
            self.user_id = message_dict["from_user"]["id"]
        else:
            self.user_id = message_dict.get("user_id")

        # Extract sentiment data
        if "sentiment" in message_dict and message_dict["sentiment"]:
            self.sentiment = SentimentWrapper(message_dict["sentiment"])
        else:
            self.sentiment = None

        # For raw_data access in create_sentiment_graph
        self.raw_data = self

    def __getitem__(self, key):
        """Support dictionary-style access: msg['key']"""
        return self._data[key]

    def __contains__(self, key):
        """Support 'key in msg' checks"""
        return key in self._data

    def get(self, key, default=None):
        """Support msg.get('key', default) calls"""
        return self._data.get(key, default)


class SentimentService:
    @staticmethod
    def get_message_repository():
        """Get message repository instance"""
        db_client = DatabaseClient.get_instance()
        return MessageRepository(db_client.client)
        
    @staticmethod
    async def analyze_chat_sentiment_by_id(chat_id: int) -> Tuple[str, Optional[io.BytesIO]]:
        """
        Analyze sentiment for a specific chat by its ID.
        
        Args:
            chat_id: The ID of the chat to analyze
            
        Returns:
            Tuple containing:
            - Analysis text
            - Graph bytes (or None if no messages)
        """
        try:
            # Get repository
            message_repository = SentimentService.get_message_repository()
            
            # Get all messages from the chat
            raw_messages = await message_repository.get_all_messages_by_chat(chat_id)
            
            log.info(f"Retrieved {len(raw_messages)} messages for sentiment analysis in chat {chat_id}")
            
            # Wrap raw message dictionaries with our wrapper class
            messages = [MessageWrapper(msg) for msg in raw_messages]
            
            # Analyze sentiment
            analysis = await SentimentService.analyze_chat_sentiment(messages)
            
            # Create sentiment graph if there are messages
            graph_bytes = None
            if messages:
                graph_bytes = await SentimentService.create_sentiment_graph(messages)
                
            return analysis, graph_bytes
            
        except Exception as e:
            log.error(f"Error in sentiment analysis service: {e}")
            raise
    @staticmethod
    async def create_sentiment_graph(messages: List[Dict]) -> io.BytesIO:
        """Create an enhanced time-based sentiment analysis graph"""
        # Convert messages to DataFrame
        df = pd.DataFrame([{"datetime": datetime.fromisoformat(msg["date"]), "positive": msg.sentiment.positive, "neutral": msg.sentiment.neutral, "negative": msg.sentiment.negative} for msg in messages if msg.sentiment])

        # Sort by datetime and set index
        df = df.sort_values(by="datetime")
        df = df.set_index("datetime")

        # Calculate rolling averages
        rolling_avgs = {window: df.rolling(window=period).mean() for window, period in GRAPH_WINDOWS.items()}

        # Calculate volatility
        volatility = df.rolling(window="24h").std()

        # Find peaks for each sentiment
        peaks = {}
        for sentiment in ["positive", "negative"]:
            values = rolling_avgs["24h"][sentiment].fillna(0)
            peak_indices, _ = find_peaks(values.values, prominence=0.1, distance=24)
            peaks[sentiment] = {"timestamps": values.index[peak_indices], "values": values.iloc[peak_indices]}

        # Create plot
        fig = plt.figure(figsize=(15, 8))
        gs = fig.add_gridspec(2, 1, height_ratios=[2, 1], hspace=0.3)
        plt.subplots_adjust(left=0.08, right=0.95)

        # Set style
        sns.set_theme(style="darkgrid")
        plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "#f0f0f0", "grid.alpha": 0.2, "grid.linestyle": ":", "axes.grid.which": "both", "axes.grid.axis": "both"})

        # Main sentiment plot
        ax1 = fig.add_subplot(gs[0])

        # Plot neutral as background
        ax1.fill_between(rolling_avgs["24h"].index, 0, rolling_avgs["24h"]["neutral"], color="gray", alpha=0.15, label="Neutral (24h avg)")
        ax1.plot(rolling_avgs["24h"].index, rolling_avgs["24h"]["neutral"], label="_nolegend_", color="gray", linewidth=1, alpha=0.5)

        # Plot sentiments
        for sentiment, color in GRAPH_COLORS.items():
            ax1.plot(rolling_avgs["24h"].index, rolling_avgs["24h"][sentiment], label=f"{sentiment.capitalize()} (24h avg)", color=color, linewidth=2, alpha=0.8)
            ax1.fill_between(rolling_avgs["24h"].index, rolling_avgs["24h"][sentiment], alpha=0.2, color=color)

            # Add peaks
            if len(peaks[sentiment]["timestamps"]) > 0:
                peak_times = peaks[sentiment]["timestamps"]
                peak_values = peaks[sentiment]["values"]
                peak_times_list = peak_times.tolist()
                peak_values_list = peak_values.tolist()

                ax1.scatter(peak_times_list, peak_values_list, color=color, s=100, zorder=5, alpha=0.6, label=f"{sentiment.capitalize()} peaks")

                # Annotate top peaks
                peak_data = sorted(zip(peak_times_list, peak_values_list), key=lambda x: x[1], reverse=True)
                for peak_time, peak_val in peak_data[: min(2, len(peak_data))]:
                    ax1.annotate(f"{peak_time.strftime('%Y-%m-%d %H:%M')}\n{peak_val:.2f}", xy=(peak_time, peak_val), xytext=(10, 10), textcoords="offset points", bbox=dict(facecolor="white", edgecolor=color, alpha=0.7), fontsize=8)

        # Volatility plot
        ax2 = fig.add_subplot(gs[1], sharex=ax1)
        volatility_filled = volatility["positive"].ffill().bfill()
        ax2.plot(volatility.index, volatility_filled, label="Emotional Volatility", color="purple", linewidth=2)
        ax2.fill_between(volatility.index, volatility_filled, alpha=0.2, color="purple")

        # Add mean volatility line
        mean_volatility = volatility["positive"].mean()
        ax2.axhline(y=mean_volatility, color="black", linestyle="--", alpha=0.5)
        ax2.annotate(f"Mean: {mean_volatility:.3f}", xy=(volatility.index[0], mean_volatility), xytext=(10, 10), textcoords="offset points", bbox=dict(facecolor="white", edgecolor="black", alpha=0.7))

        # Format axes
        ax1.set_ylabel("Sentiment Score", fontsize=12)
        ax1.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
        ax1.grid(True, which="both")
        ax1.minorticks_on()
        ax1.margins(x=0)
        ax2.margins(x=0)
        ax2.set_ylabel("Volatility", fontsize=12)
        ax2.grid(True, which="both")
        ax2.minorticks_on()

        for ax in [ax1, ax2]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.%Y"))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

        # Add stats textbox
        stats_text = f"Total Messages: {len(df)}\nAvg Sentiment: {df.mean().round(3).to_dict()}\nPeak Count: {sum(len(p) for p in peaks.values())}"
        fig.text(0.02, 0.98, stats_text, fontsize=8, bbox=dict(facecolor="white", edgecolor="gray", alpha=0.8))

        # Save plot
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=300, bbox_inches="tight", pad_inches=0.2)
        buf.seek(0)
        plt.close()

        return buf

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean text for comparison"""
        return " ".join(text.lower().split())

    @staticmethod
    def is_valid_text(text: str) -> bool:
        """Check if text is valid for analysis"""
        return text and MIN_TEXT_LENGTH <= len(text.strip()) <= MAX_TEXT_LENGTH

    @staticmethod
    async def analyze_chat_sentiment(messages: List[Dict]) -> str:
        """Analyze sentiment of chat messages"""
        if not messages:
            return MESSAGES["SENTIMENT_NO_MESSAGES"]

        # Initialize counters and trackers
        stats = {"total_messages": 0, "filtered_messages": 0, "skipped_no_sentiment": 0, "skipped_no_chat": 0, "skipped_bot_replies": 0, "skipped_wrong_chat_type": 0, "skipped_forwarded": 0, "duplicate_count": 0}

        user_sentiments = defaultdict(lambda: {"negative": 0.0, "neutral": 0.0, "positive": 0.0, "count": 0})
        user_topics = defaultdict(lambda: defaultdict(int))
        user_message_count = defaultdict(int)
        sensitive_topics = defaultdict(int)
        top_texts = {"positive": [], "negative": [], "neutral": [], "topics": defaultdict(list)}
        seen_texts_lower = set()

        # Process messages
        for msg in messages:
            stats["total_messages"] += 1

            if "forward_from_chat" in msg:
                stats["skipped_forwarded"] += 1
                continue

            if not msg.sentiment:
                stats["skipped_no_sentiment"] += 1
                continue

            if "chat" not in msg or "type" not in msg["chat"]:
                stats["skipped_no_chat"] += 1
                continue

            chat_type = msg["chat"]["type"]
            if chat_type not in ["ChatType.SUPERGROUP", "ChatType.GROUP"]:
                stats["skipped_wrong_chat_type"] += 1
                continue

            user_id = msg.user_id
            # Get username with fallbacks
            username = None
            if "from_user" in msg:
                from_user = msg["from_user"]
                username = (
                    from_user.get("username")  # Try username first
                    or from_user.get("first_name")  # Then first_name
                    or f"user_{user_id}"  # Finally fall back to user_id
                )
            else:
                username = f"user_{user_id}"

            text = msg.get("text", "").strip()

            if "reply_to_message" in msg and "from_user" in msg["reply_to_message"] and msg["reply_to_message"]["from_user"].get("is_bot", False):
                stats["skipped_bot_replies"] += 1
                continue

            cleaned_text = SentimentService.clean_text(text)
            if cleaned_text in seen_texts_lower:
                stats["duplicate_count"] += 1
                continue

            seen_texts_lower.add(cleaned_text)
            stats["filtered_messages"] += 1

            # Update sentiment scores
            user_sentiments[username]["negative"] += msg.sentiment.negative
            user_sentiments[username]["neutral"] += msg.sentiment.neutral
            user_sentiments[username]["positive"] += msg.sentiment.positive
            user_sentiments[username]["count"] += 1
            user_message_count[username] += 1

            # Track top texts
            if SentimentService.is_valid_text(text):
                sentiment_scores = {"positive": msg.sentiment.positive, "negative": msg.sentiment.negative, "neutral": msg.sentiment.neutral}
                max_sentiment = max(sentiment_scores.items(), key=lambda x: x[1])

                if max_sentiment[1] >= SENTIMENT_THRESHOLD:
                    top_texts[max_sentiment[0]].append((text, max_sentiment[1]))

                # Track sensitive topics
                for topic, score in msg.sentiment.sensitive_topics.items():
                    if score > SENTIMENT_THRESHOLD and topic.lower() != "none":
                        user_topics[username][topic] += 1
                        sensitive_topics[topic] += 1
                        if score > TOPIC_THRESHOLD:
                            top_texts["topics"][topic].append((text, score))

        return SentimentService._format_analysis_results(stats, user_sentiments, user_topics, user_message_count, sensitive_topics, top_texts)

    @staticmethod
    def _format_analysis_results(stats: Dict, user_sentiments: Dict, user_topics: Dict, user_message_count: Dict, sensitive_topics: Dict, top_texts: Dict) -> str:
        """Format analysis results into a readable string"""
        if not user_sentiments:
            return MESSAGES["SENTIMENT_NO_DATA"]

        # Calculate user averages
        user_avg_sentiments = []
        for username, scores in user_sentiments.items():
            if scores["count"] > 0:
                avg_negative = scores["negative"] / scores["count"]
                avg_positive = scores["positive"] / scores["count"]
                avg_neutral = scores["neutral"] / scores["count"]

                base_score = avg_positive - avg_negative
                intensity_factor = 1 - (avg_neutral * 0.5)
                volatility = (avg_positive + avg_negative) * (1 - avg_neutral)
                sentiment_score = base_score * intensity_factor

                user_avg_sentiments.append({"username": username, "sentiment_score": sentiment_score, "volatility": volatility, "avg_negative": avg_negative, "avg_positive": avg_positive, "avg_neutral": avg_neutral, "message_count": scores["count"]})

        # Format results
        result = [
            "📊 <b>Анализ тональности чата:</b>\n",
            f"Всего загружено сообщений: {stats['total_messages']}\n",
            f"Сообщений после фильтрации: {stats['filtered_messages']}\n",
            f"Пропущено переадресованных сообщений: {stats['skipped_forwarded']}\n",
            f"Повторяющихся сообщений: {stats['duplicate_count']}\n",
        ]

        # Filter and sort users
        filtered_users = [u for u in user_avg_sentiments if u["message_count"] >= MIN_MESSAGES]
        negative_users = sorted(filtered_users, key=lambda x: x["avg_negative"], reverse=True)[:5]
        positive_users = sorted(filtered_users, key=lambda x: x["avg_positive"], reverse=True)[:5]
        volatile_users = sorted(filtered_users, key=lambda x: x["volatility"], reverse=True)[:5]

        # Add user rankings
        result.extend(SentimentService._format_user_rankings(negative_users, positive_users, volatile_users))

        # Add topic statistics
        result.extend(SentimentService._format_topic_stats(user_topics, user_message_count, sensitive_topics))

        # Add top messages
        result.extend(SentimentService._format_top_messages(top_texts, sensitive_topics))

        return "".join(result)

    @staticmethod
    def _format_user_rankings(negative_users, positive_users, volatile_users) -> List[str]:
        """Format user rankings section"""
        result = []

        # Negative users
        result.append(f"\n😠 <b>Самые негативные:</b> (мин. {MIN_MESSAGES} сообщений)")
        for user in negative_users:
            # Format username - only add @ if it looks like a username
            display_name = user["username"]
            if not display_name.startswith(("user_", "@")):
                display_name = f"@{display_name}"

            result.append(f"\n{display_name}: {user['avg_negative']:.2%} neg, {user['avg_neutral']:.2%} neut, {user['message_count']} msgs")

        # Positive users
        result.append(f"\n\n😊 <b>Самые позитивные:</b> (мин. {MIN_MESSAGES} сообщений)")
        for user in positive_users:
            display_name = user["username"]
            if not display_name.startswith(("user_", "@")):
                display_name = f"@{display_name}"

            result.append(f"\n{display_name}: {user['avg_positive']:.2%} pos, {user['avg_neutral']:.2%} neut, {user['message_count']} msgs")

        # Volatile users
        result.append(f"\n\n🎭 <b>Самые эмоциональные:</b> (мин. {MIN_MESSAGES} сообщений)")
        for user in volatile_users:
            display_name = user["username"]
            if not display_name.startswith(("user_", "@")):
                display_name = f"@{display_name}"

            result.append(f"\n{display_name}: {user['volatility']:.2%} volatility (pos: {user['avg_positive']:.2%}, neg: {user['avg_negative']:.2%}, neut: {user['avg_neutral']:.2%}, {user['message_count']} msgs)")

        return result

    @staticmethod
    def _format_topic_stats(user_topics, user_message_count, sensitive_topics) -> List[str]:
        """Format topic statistics section"""
        result = ["\n\n⚠️ <b>Преступники:</b>"]

        user_topic_stats = []
        for username, topics in user_topics.items():
            total_mentions = sum(topics.values())
            if total_mentions > 0:
                percentage = (total_mentions / user_message_count[username]) * 100
                user_topic_stats.append((username, total_mentions, percentage))

        user_topic_stats.sort(key=lambda x: x[1], reverse=True)
        for username, mentions, percentage in user_topic_stats[:5]:
            # Format username - only add @ if it looks like a username
            display_name = username
            if not display_name.startswith(("user_", "@")):
                display_name = f"@{display_name}"

            user_top_topics = sorted(user_topics[username].items(), key=lambda x: x[1], reverse=True)[:3]
            top_topics_str = ", ".join(f"{topic}: {count}" for topic, count in user_top_topics)
            result.append(f"\n{display_name}: {mentions} mentions ({percentage:.1f}% of messages)")
            result.append(f"\n  Top topics: {top_topics_str}")

        return result

    @staticmethod
    def _format_top_messages(top_texts: Dict, sensitive_topics: Dict) -> List[str]:
        """Format top messages section"""
        result = ["\n\n📝 <b>Топ сообщений по категориям:</b>"]

        # Positive messages
        result.append("\n\n😊 <b>Позитивные сообщения:</b>")
        for text, score in sorted(top_texts["positive"], key=lambda x: x[1], reverse=True)[:5]:
            result.append(f"\n• {text} (score: {score:.2%})")

        # Negative messages
        result.append("\n\n😠 <b>Негативные сообщения:</b>")
        for text, score in sorted(top_texts["negative"], key=lambda x: x[1], reverse=True)[:5]:
            result.append(f"\n• {text} (score: {score:.2%})")

        # Topic messages
        if top_texts["topics"]:
            result.append("\n\n🎯 <b>Сообщения по темам:</b>")
            top_topics = sorted(sensitive_topics.items(), key=lambda x: x[1], reverse=True)[:5]
            for topic, mentions in top_topics:
                result.append(f"\n\n<b>{topic}</b> (total mentions: {mentions}):")
                top_topic_texts = sorted(top_texts["topics"][topic], key=lambda x: x[1], reverse=True)[:3]
                for text, score in top_topic_texts:
                    result.append(f"\n• {text} (score: {score:.2%})")

        return result
