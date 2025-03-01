# Russian messages only as per requirements
MESSAGES = {
    "SENTIMENT_PRIVATE_CHAT": "Эта команда может быть использована только в группах или супергруппах.",
    "SENTIMENT_ANALYZING": "📊 Анализирую чат... Пожалуйста подождите",
    "SENTIMENT_NO_DATA": "Нет данных о настроениях в сообщениях.",
    "SENTIMENT_NO_MESSAGES": "Сообщения не найдены в этом чате.",
    "SENTIMENT_GRAPH_CAPTION": ("📊 Анализ настроений в чате\n\n📈 График показывает:\n• Тренды позитивных и негативных настроений (24ч)\n• Индекс эмоциональной волатильности"),
}

# Analysis settings
MIN_MESSAGES = 50  # Minimum messages for user rankings
MIN_TEXT_LENGTH = 10  # Minimum text length for analysis
MAX_TEXT_LENGTH = 150  # Maximum text length for analysis
SENTIMENT_THRESHOLD = 0.7  # Minimum threshold for significant sentiment
TOPIC_THRESHOLD = 0.9  # Threshold for topic relevance

# Graph settings
GRAPH_WINDOWS = {"6h": "6h", "24h": "24h", "7d": "7d"}

GRAPH_COLORS = {"positive": "green", "negative": "red"}
