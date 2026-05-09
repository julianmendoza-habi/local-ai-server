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

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Comma-separated emails that bypass the allowlist and get is_admin=true
    # e.g. ADMIN_EMAILS=julian@habi.co,otro@gmail.com
    # Stored as raw string to avoid pydantic-settings JSON-parsing issues
    admin_emails: str = ""

    def is_admin_email(self, email: str) -> bool:
        if not self.admin_emails:
            return False
        return email.lower() in {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


settings = Settings()
