import pytest
from cryptography.fernet import Fernet

from helio.core.config import (
    ConfigError,
    Settings,
    optional_config_warnings,
    validate_startup_config,
)


def _cfg(**overrides) -> Settings:
    """Build a fully specified Settings instance, ignoring .env and OS env vars.

    Every field consulted by validation is passed explicitly so a developer's
    real environment cannot influence the outcome.

    Args:
        **overrides: Field values to replace in the valid baseline.

    Returns:
        A Settings instance.
    """
    baseline = {
        "database_url": "postgresql+asyncpg://helio:secret@db:5432/helio",
        "fernet_key": Fernet.generate_key().decode(),
        "irradiance_source": "nasa",
        "nrel_api_key": "",
        "enphase_client_id": "client-id",
        "enphase_client_secret": "client-secret",
    }
    return Settings(_env_file=None, **{**baseline, **overrides})


def test_valid_config_passes():
    validate_startup_config(_cfg())


def test_missing_fernet_key_names_the_variable():
    with pytest.raises(ConfigError) as exc_info:
        validate_startup_config(_cfg(fernet_key=""))
    assert "FERNET_KEY" in str(exc_info.value)
    assert "generate-fernet-key" in str(exc_info.value)


def test_malformed_fernet_key_is_rejected():
    with pytest.raises(ConfigError) as exc_info:
        validate_startup_config(_cfg(fernet_key="not-a-fernet-key"))
    assert "FERNET_KEY" in str(exc_info.value)


def test_fernet_key_of_wrong_length_is_rejected():
    # Valid base64 but only 16 bytes, so Fernet rejects it.
    with pytest.raises(ConfigError) as exc_info:
        validate_startup_config(_cfg(fernet_key="AAAAAAAAAAAAAAAAAAAAAA=="))
    assert "FERNET_KEY" in str(exc_info.value)


def test_nrel_source_without_api_key_names_both_variables():
    with pytest.raises(ConfigError) as exc_info:
        validate_startup_config(_cfg(irradiance_source="nrel", nrel_api_key=""))
    message = str(exc_info.value)
    assert "IRRADIANCE_SOURCE" in message
    assert "NREL_API_KEY" in message


def test_nrel_source_with_api_key_passes():
    validate_startup_config(_cfg(irradiance_source="nrel", nrel_api_key="key"))


def test_nasa_source_without_nrel_key_passes():
    validate_startup_config(_cfg(irradiance_source="nasa", nrel_api_key=""))


@pytest.mark.parametrize("source", ["NREL", "openweather", ""])
def test_unknown_irradiance_source_is_rejected(source):
    with pytest.raises(ConfigError) as exc_info:
        validate_startup_config(_cfg(irradiance_source=source))
    assert "IRRADIANCE_SOURCE" in str(exc_info.value)


def test_empty_database_url_is_rejected():
    with pytest.raises(ConfigError) as exc_info:
        validate_startup_config(_cfg(database_url=""))
    assert "DATABASE_URL" in str(exc_info.value)


def test_database_url_without_async_driver_is_rejected():
    with pytest.raises(ConfigError) as exc_info:
        validate_startup_config(
            _cfg(database_url="postgresql://helio:secret@db:5432/helio")
        )
    assert "postgresql+asyncpg://" in str(exc_info.value)


def test_database_url_error_does_not_leak_the_password():
    with pytest.raises(ConfigError) as exc_info:
        validate_startup_config(
            _cfg(database_url="postgresql://helio:supersecret@db:5432/helio")
        )
    assert "supersecret" not in str(exc_info.value)


def test_all_errors_are_reported_together():
    with pytest.raises(ConfigError) as exc_info:
        validate_startup_config(
            _cfg(database_url="", fernet_key="", irradiance_source="nrel")
        )
    message = str(exc_info.value)
    assert "DATABASE_URL" in message
    assert "FERNET_KEY" in message
    assert "NREL_API_KEY" in message


def test_enphase_configured_true_when_credentials_present():
    assert _cfg().enphase_configured is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"enphase_client_id": ""},
        {"enphase_client_secret": ""},
        {"enphase_client_id": "", "enphase_client_secret": ""},
    ],
)
def test_enphase_configured_false_when_a_credential_is_missing(overrides):
    assert _cfg(**overrides).enphase_configured is False


def test_missing_enphase_credentials_warn_instead_of_failing():
    cfg = _cfg(enphase_client_id="")
    validate_startup_config(cfg)
    warnings = optional_config_warnings(cfg)
    assert len(warnings) == 1
    assert "ENPHASE_CLIENT_ID" in warnings[0]


def test_no_warnings_when_fully_configured():
    assert optional_config_warnings(_cfg()) == []
