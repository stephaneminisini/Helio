from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

IRRADIANCE_SOURCES = ("nasa", "manual")
ASYNC_DRIVER_PREFIX = "postgresql+asyncpg://"
FERNET_KEY_HINT = (
    "Generate one with `make generate-fernet-key` and set FERNET_KEY in .env"
)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://helio:changeme@db:5432/helio"
    enphase_client_id: str = ""
    enphase_client_secret: str = ""
    enphase_system_id: str = ""
    enphase_access_token: str = ""
    enphase_refresh_token: str = ""
    # Must match a redirect URI registered on the Enphase application: the
    # consent request and the code exchange both send it, and Enphase compares
    # them. It goes through the dashboard's origin, which proxies /api to here,
    # because that is the origin the browser can reach.
    enphase_redirect_uri: str = "http://localhost:3000/api/auth/enphase/callback"
    # Where the OAuth callback sends the browser once the exchange is done.
    frontend_base_url: str = "http://localhost:3000"
    fernet_key: str = ""
    irradiance_source: str = "nasa"
    poll_hour: int = 4
    poll_minute: int = 0
    tz: str = "America/Montreal"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

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

    @property
    def enphase_configured(self) -> bool:
        """Whether the Enphase application credentials are both present."""
        return bool(self.enphase_client_id and self.enphase_client_secret)


def _database_url_errors(url: str) -> list[str]:
    """Validate the database URL without exposing the password it contains.

    Args:
        url: The configured DATABASE_URL value.

    Returns:
        A list of human-readable problems; empty when the value is usable.
    """
    if not url:
        return ["DATABASE_URL is not set"]
    if not url.startswith(ASYNC_DRIVER_PREFIX):
        scheme = url.split("://", 1)[0]
        return [
            f"DATABASE_URL must start with {ASYNC_DRIVER_PREFIX} "
            f"(got '{scheme}://'); SQLAlchemy needs the async driver prefix"
        ]
    return []


def _fernet_key_errors(key: str) -> list[str]:
    """Validate that the Fernet key is present and well-formed.

    Args:
        key: The configured FERNET_KEY value.

    Returns:
        A list of human-readable problems; empty when the key is usable.
    """
    if not key:
        return [f"FERNET_KEY is not set. {FERNET_KEY_HINT}"]
    try:
        Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        return [f"FERNET_KEY is not a valid Fernet key ({exc}). {FERNET_KEY_HINT}"]
    return []


def _irradiance_errors(source: str) -> list[str]:
    """Validate the irradiance source.

    An unrecognised value such as 'NASA' would otherwise be stored on new
    systems and then skip the irradiance step on every poll.

    Args:
        source: The configured IRRADIANCE_SOURCE value.

    Returns:
        A list of human-readable problems; empty when the value is usable.
    """
    if source not in IRRADIANCE_SOURCES:
        return [
            f"IRRADIANCE_SOURCE must be one of {', '.join(IRRADIANCE_SOURCES)} "
            f"(got '{source}')"
        ]
    return []


def validate_startup_config(cfg: Settings) -> None:
    """Check the configuration the application cannot run without.

    Args:
        cfg: The settings instance to validate.

    Raises:
        ConfigError: If any required variable is missing or malformed. Every
            problem found is listed in the message so a misconfigured install
            can be fixed in one pass.
    """
    errors = [
        *_database_url_errors(cfg.database_url),
        *_fernet_key_errors(cfg.fernet_key),
        *_irradiance_errors(cfg.irradiance_source),
    ]
    if errors:
        raise ConfigError(
            "Invalid configuration:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def optional_config_warnings(cfg: Settings) -> list[str]:
    """Return warnings for configuration that is only needed once connected.

    Args:
        cfg: The settings instance to inspect.

    Returns:
        A list of warning messages; empty when nothing is missing.
    """
    if cfg.enphase_configured:
        return []
    return [
        "ENPHASE_CLIENT_ID / ENPHASE_CLIENT_SECRET are not set - Enphase is not "
        "connected and no production data will be polled. Add them to .env, "
        "then restart the API."
    ]


settings = Settings()
