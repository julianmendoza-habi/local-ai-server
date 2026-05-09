from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    ollama_base_url: str
    default_model: str
    allowed_models: list[str]

    max_concurrent_ollama_requests: int = 2
    max_queue_size: int = 10
    request_timeout_seconds: float = 120.0

    max_messages_per_session: int = 20
    ollama_keep_alive: int = -1

    database_url: str | None = None


settings = Settings()
