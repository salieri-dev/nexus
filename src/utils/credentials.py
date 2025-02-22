from dataclasses import dataclass
from typing import Optional
import os
from urllib.parse import quote_plus


@dataclass
class ProxyConfig:
    enabled: bool
    host: Optional[str]
    port: Optional[int]

    @classmethod
    def from_env(cls) -> 'ProxyConfig':
        return cls(
            enabled=os.getenv("USE_PROXY", "false").lower() == "true",
            host=os.getenv("PROXY_HOST"),
            port=int(os.getenv("PROXY_PORT", "0")) if os.getenv("PROXY_PORT") else None
        )


@dataclass
class DatabaseConfig:
    username: str
    password: str
    host: str
    port: int

    @property
    def connection_string(self) -> str:
        username = quote_plus(self.username)
        password = quote_plus(self.password)
        return (
            f"mongodb://{username}:{password}@{self.host}:{self.port}"
            if username and password
            else f"mongodb://{self.host}:{self.port}"
        )

    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        # Use service name in Docker, fallback to MONGO_BIND_IP
        host = os.getenv("MONGO_HOST", "mongodb") if os.getenv("DOCKER_ENV") else os.getenv("MONGO_BIND_IP",
                                                                                            "localhost")
        return cls(
            username=os.getenv("MONGO_USERNAME", ""),
            password=os.getenv("MONGO_PASSWORD", ""),
            host=host,
            port=int(os.getenv("MONGO_PORT", "27017"))
        )


@dataclass
class BotConfig:
    name: str
    app_id: int
    app_hash: str
    bot_token: str

    @classmethod
    def from_env(cls) -> 'BotConfig':
        return cls(
            name=os.getenv("NAME", "pyrogram"),
            app_id=int(os.getenv("APP_ID", "0")),
            app_hash=os.getenv("APP_HASH", ""),
            bot_token=os.getenv("BOT_TOKEN", "")
        )


@dataclass
class APIConfig:
    fal_key: str
    openrouter_key: str
    gemini_key: str
    suno_api_url: str

    @classmethod
    def from_env(cls) -> 'APIConfig':
        return cls(
            fal_key=os.getenv("FAL_KEY", ""),
            openrouter_key=os.getenv("OPENROUTER_API_KEY", ""),
            gemini_key=os.getenv("GEMINI_API_KEY", ""),
            suno_api_url=os.getenv("SUNO_API_URL", "")
        )


@dataclass
class DebugConfig:
    owner_id: int

    @classmethod
    def from_env(cls) -> 'DebugConfig':
        return cls(
            owner_id=int(os.getenv("OWNER_ID", "0"))
        )


@dataclass
class Credentials:
    bot: BotConfig
    database: DatabaseConfig
    proxy: ProxyConfig
    api: APIConfig
    debug: DebugConfig

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'Credentials':
        if not cls._instance:
            cls._instance = cls.from_env()
        return cls._instance

    @classmethod
    def from_env(cls) -> 'Credentials':
        return cls(
            bot=BotConfig.from_env(),
            database=DatabaseConfig.from_env(),
            proxy=ProxyConfig.from_env(),
            api=APIConfig.from_env(),
            debug=DebugConfig.from_env()
        )
