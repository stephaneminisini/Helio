from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import respx
from cryptography.fernet import Fernet
from loguru import logger

from helio.core.config import settings
from helio.core.crypto import decrypt, encrypt
from helio.db.models import System
from helio.ingestion.tokens import (
    REFRESH_TOKEN_LIFETIME_DAYS,
    REFRESH_TOKEN_WARN_AFTER_DAYS,
    TokenError,
    build_authenticated_client,
    load_tokens,
    refresh_token_age_warning,
    save_tokens,
)

TOKEN_URL = "https://api.enphaseenergy.com/oauth/token"


@pytest.fixture
def key(monkeypatch):
    """Install a fresh Fernet key in the application settings."""
    value = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "fernet_key", value)
    return value


@pytest.fixture
def env_tokens(monkeypatch):
    """Populate the bootstrap tokens that live in .env."""
    monkeypatch.setattr(settings, "enphase_access_token", "env-access")
    monkeypatch.setattr(settings, "enphase_refresh_token", "env-refresh")


@pytest.fixture
def credentials(monkeypatch):
    """Populate the Enphase application credentials."""
    monkeypatch.setattr(settings, "enphase_client_id", "client-id")
    monkeypatch.setattr(settings, "enphase_client_secret", "client-secret")


@pytest.fixture
def captured_logs():
    """Capture everything written to the logger for the duration of a test."""
    lines: list[str] = []
    sink_id = logger.add(lines.append, level="DEBUG")
    yield lines
    logger.remove(sink_id)


def _system(**overrides) -> System:
    """Build an unpersisted System row."""
    defaults = {
        "id": 1,
        "enphase_system_id": "sys-001",
        "install_date": date(2023, 1, 1),
    }
    return System(**{**defaults, **overrides})


def test_load_tokens_prefers_the_encrypted_database_values(key, env_tokens):
    system = _system(
        enphase_access_token=encrypt("db-access", key),
        enphase_refresh_token=encrypt("db-refresh", key),
    )

    assert load_tokens(system) == ("db-access", "db-refresh")


def test_load_tokens_bootstraps_from_env_when_columns_are_empty(key, env_tokens):
    assert load_tokens(_system()) == ("env-access", "env-refresh")


def test_load_tokens_bootstraps_refresh_token_when_only_access_is_stored(
    key, env_tokens
):
    system = _system(enphase_access_token=encrypt("db-access", key))

    assert load_tokens(system) == ("db-access", "env-refresh")


def test_load_tokens_raises_when_no_refresh_token_is_available(key, monkeypatch):
    monkeypatch.setattr(settings, "enphase_refresh_token", "")

    with pytest.raises(TokenError) as exc_info:
        load_tokens(_system())
    assert "ENPHASE_REFRESH_TOKEN" in str(exc_info.value)


def test_load_tokens_error_is_actionable_when_the_key_cannot_decrypt(key, monkeypatch):
    """AC5: a rotated or lost FERNET_KEY produces a specific, actionable error."""
    system = _system(
        enphase_access_token=encrypt("db-access", key),
        enphase_refresh_token=encrypt("db-refresh", key),
    )
    monkeypatch.setattr(settings, "fernet_key", Fernet.generate_key().decode())

    with pytest.raises(TokenError) as exc_info:
        load_tokens(system)
    message = str(exc_info.value)
    assert "FERNET_KEY" in message
    assert "reconnect" in message.lower()


def test_load_tokens_raises_token_error_on_a_malformed_stored_value(key):
    system = _system(
        enphase_access_token="not-ciphertext",
        enphase_refresh_token="not-ciphertext",
    )

    with pytest.raises(TokenError):
        load_tokens(system)


async def test_save_tokens_persists_ciphertext_not_plaintext(key):
    system = _system()
    session = AsyncMock()

    await save_tokens(session, system, "new-access", "new-refresh")

    assert system.enphase_access_token != "new-access"
    assert system.enphase_refresh_token != "new-refresh"
    assert decrypt(system.enphase_access_token, key) == "new-access"
    assert decrypt(system.enphase_refresh_token, key) == "new-refresh"
    session.commit.assert_awaited_once()


async def test_save_tokens_stamps_the_rotation_time(key):
    system = _system()

    await save_tokens(AsyncMock(), system, "new-access", "new-refresh")

    assert system.token_updated_at is not None
    assert (datetime.now(tz=UTC) - system.token_updated_at) < timedelta(minutes=1)


async def test_save_tokens_keeps_plaintext_out_of_the_logs(key, captured_logs):
    """AC1: the plaintext must appear nowhere in the logs."""
    await save_tokens(AsyncMock(), _system(), "sensitive-access", "sensitive-refresh")

    assert captured_logs, "expected the rotation to be logged"
    combined = "".join(captured_logs)
    assert "sensitive-access" not in combined
    assert "sensitive-refresh" not in combined


async def test_saved_tokens_round_trip_through_load(key):
    system = _system()

    await save_tokens(AsyncMock(), system, "round-access", "round-refresh")

    assert load_tokens(system) == ("round-access", "round-refresh")


def test_no_age_warning_before_the_threshold():
    stamped = datetime(2026, 8, 1, tzinfo=UTC)
    system = _system(token_updated_at=stamped)
    now = stamped + timedelta(days=REFRESH_TOKEN_WARN_AFTER_DAYS - 1)

    assert refresh_token_age_warning(system, now=now) is None


def test_no_age_warning_when_never_rotated():
    assert refresh_token_age_warning(_system(), now=datetime.now(tz=UTC)) is None


def test_age_warning_names_the_days_remaining():
    """AC4: a token older than 25 days warns, naming the days remaining."""
    stamped = datetime(2026, 8, 1, tzinfo=UTC)
    system = _system(token_updated_at=stamped)
    now = stamped + timedelta(days=REFRESH_TOKEN_WARN_AFTER_DAYS)

    warning = refresh_token_age_warning(system, now=now)

    assert warning is not None
    remaining = REFRESH_TOKEN_LIFETIME_DAYS - REFRESH_TOKEN_WARN_AFTER_DAYS
    assert str(remaining) in warning


def test_age_warning_reports_zero_days_once_expired():
    stamped = datetime(2026, 8, 1, tzinfo=UTC)
    system = _system(token_updated_at=stamped)
    now = stamped + timedelta(days=REFRESH_TOKEN_LIFETIME_DAYS + 5)

    warning = refresh_token_age_warning(system, now=now)

    assert warning is not None
    assert "-" not in warning.split("expire")[-1]


@respx.mock
async def test_build_client_persists_the_rotated_tokens(key, env_tokens, credentials):
    """AC1 and AC3: bootstrap from env, then persist what Enphase returns."""
    respx.post(TOKEN_URL).mock(
        return_value=respx.MockResponse(
            200, json={"access_token": "rotated-access", "refresh_token": "rotated-ref"}
        )
    )
    system = _system()
    session = AsyncMock()

    client = await build_authenticated_client(session, system)

    assert client.access_token == "rotated-access"
    assert decrypt(system.enphase_access_token, key) == "rotated-access"
    assert decrypt(system.enphase_refresh_token, key) == "rotated-ref"
    session.commit.assert_awaited_once()


@respx.mock
async def test_build_client_uses_stored_tokens_after_a_restart(
    key, credentials, monkeypatch
):
    """AC2: a restart must use the persisted token, not the stale one in .env."""
    monkeypatch.setattr(settings, "enphase_refresh_token", "stale-env-refresh")
    system = _system(enphase_refresh_token=encrypt("stored-refresh", key))
    route = respx.post(TOKEN_URL).mock(
        return_value=respx.MockResponse(
            200, json={"access_token": "access-2", "refresh_token": "refresh-2"}
        )
    )

    await build_authenticated_client(AsyncMock(), system)

    sent = route.calls.last.request.content.decode()
    assert "stored-refresh" in sent
    assert "stale-env-refresh" not in sent


@respx.mock
async def test_build_client_sends_the_system_id_from_the_database(
    key, env_tokens, credentials, monkeypatch
):
    monkeypatch.setattr(settings, "enphase_system_id", "env-system-id")
    respx.post(TOKEN_URL).mock(
        return_value=respx.MockResponse(
            200, json={"access_token": "a", "refresh_token": "r"}
        )
    )

    client = await build_authenticated_client(
        AsyncMock(), _system(enphase_system_id="db-system-id")
    )

    assert client.system_id == "db-system-id"


@respx.mock
async def test_build_client_keeps_rotated_tokens_out_of_the_logs(
    key, env_tokens, credentials, captured_logs
):
    respx.post(TOKEN_URL).mock(
        return_value=respx.MockResponse(
            200, json={"access_token": "secret-a", "refresh_token": "secret-r"}
        )
    )

    await build_authenticated_client(AsyncMock(), _system())

    combined = "".join(captured_logs)
    assert "secret-a" not in combined
    assert "secret-r" not in combined


@respx.mock
async def test_build_client_logs_the_age_warning(
    key, env_tokens, credentials, captured_logs
):
    respx.post(TOKEN_URL).mock(
        return_value=respx.MockResponse(
            200, json={"access_token": "a", "refresh_token": "r"}
        )
    )
    stale = datetime.now(tz=UTC) - timedelta(days=REFRESH_TOKEN_WARN_AFTER_DAYS + 1)

    await build_authenticated_client(AsyncMock(), _system(token_updated_at=stale))

    assert any("refresh token" in line.lower() for line in captured_logs)


async def test_build_client_raises_token_error_before_calling_enphase(key, monkeypatch):
    """An undecryptable token must fail fast, without an HTTP call."""
    monkeypatch.setattr(settings, "enphase_refresh_token", "")
    system = _system(enphase_refresh_token="not-ciphertext")

    with pytest.raises(TokenError):
        await build_authenticated_client(AsyncMock(), system)
