from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://helio:changeme@db:5432/helio"
    enphase_client_id: str = ""
    enphase_client_secret: str = ""
    enphase_system_id: str = ""
    fernet_key: str = ""
    nrel_api_key: str = ""
    irradiance_source: str = "nrel"
    poll_hour: int = 4
    poll_minute: int = 0
    tz: str = "America/Montreal"
    vite_api_base_url: str = "http://localhost:8000"


settings = Settings()
