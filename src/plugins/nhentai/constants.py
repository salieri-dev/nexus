import os

# URLs and API constants
PROXY_URL = f"socks5://{os.getenv('PROXY_HOST')}:{os.getenv('PROXY_PORT')}"
NHENTAI_URL_PATTERN = r"https?://nhentai\.net/g/(\d+)"
MAX_RETRIES = 2

# Image domains for fallback
NHENTAI_IMAGE_DOMAINS = ["i2.nhentai.net", "i1.nhentai.net", "i3.nhentai.net"]
NHENTAI_THUMB_DOMAINS = ["i2.nhentai.net", "i1.nhentai.net", "i3.nhentai.net"]

# Content filtering
BLACKLIST_TAGS = ["lolicon", "shotacon", "guro", "rape", "scat", "urination", "ryona", "piss drinking", "torture"]

# Message constants
NSFW_DISABLED_MESSAGE = "❌ NSFW контент отключен в этом чате. Администратор может включить его через /config"
NHENTAI_DOWN_MESSAGE = "NHentai недоступен"
NO_RESULTS_MESSAGE = "Не найдено результатов для '{query}'"
