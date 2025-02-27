import httpx
from openai import AsyncOpenAI
from structlog import get_logger

from src.utils.credentials import Credentials

log = get_logger(name=__name__)

HEADERS = {
    "HTTP-Referer": "http://salieri.dev",
    "X-Title": "Nexus"
}


class OpenRouter:
    """Base OpenAI service providing core functionality"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OpenRouter, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._init_client()
            self._initialized = True

    def _init_client(self) -> None:
        credentials = Credentials.get_instance()
        proxy_config = credentials.proxy

        transport = httpx.HTTPTransport(retries=3, verify=False)
        http_client_args = {
            "timeout": 120.0,
            "transport": transport,
        }

        if proxy_config.enabled and proxy_config.host and proxy_config.port:
            proxy_url = f"socks5://{proxy_config.host}:{proxy_config.port}"
            http_client_args["proxy"] = proxy_url

        self._client = AsyncOpenAI(
            http_client=httpx.AsyncClient(**http_client_args),
            api_key=credentials.api.openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=HEADERS
        )

    @property
    def client(self) -> AsyncOpenAI:
        """Get the OpenAI client"""
        return self._client