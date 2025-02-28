"""Constants for the fanfic plugin"""

# Rate limiting constants
RATE_LIMIT_WINDOW_SECONDS = 45
RATE_LIMIT_OPERATION = "fanfic_handler"

# Message constants
MESSAGES = {
    "WAIT_MESSAGE": "⚙️ Генерирую фанфик...",
    "RATE_LIMITED": "🕒 Подождите 45 секунд перед следующим запросом!",
    "MISSING_TOPIC": "❌ Пожалуйста, укажите тему для фанфика после команды /fanfic",
    "TOPIC_TOO_SHORT": "❌ Тема слишком короткая! Минимум 3 символа.",
    "GENERATION_FAILED": "❌ Не удалось сгенерировать фанфик. Попробуйте позже.",
}

# Validation constants
MIN_TOPIC_LENGTH = 3

# Generation constants
DEFAULT_TEMPERATURE = 0.8
MAX_TOKENS = 4000

# Message formatting
MAX_MESSAGE_LENGTH = 4000
