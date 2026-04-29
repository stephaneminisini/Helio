from pydantic import field_validator
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

    @field_validator("poll_hour")
    @classmethod
    def validate_poll_hour(cls, v: int) -> int:
        """Validate poll_hour is a valid 24-hour value.

        Args:
            v: The poll_hour value.

        Returns:
            The validated value.

        Raises:
            ValueError: If the value is not between 0 and 23.
        """
        if not 0 <= v <= 23:
            raise ValueError(f"poll_hour must be 0-23, got {v}")
        return v

    @field_validator("poll_minute")
    @classmethod
    def validate_poll_minute(cls, v: int) -> int:
        """Validate poll_minute is a valid minute value.

        Args:
            v: The poll_minute value.

        Returns:
            The validated value.

        Raises:
            ValueError: If the value is not between 0 and 59.
        """
        if not 0 <= v <= 59:
            raise ValueError(f"poll_minute must be 0-59, got {v}")
        return v


settings = Settings()
