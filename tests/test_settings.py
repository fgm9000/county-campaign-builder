"""Settings: environment parsing and the live-mode secret check."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from county_campaign_builder.settings import DEFAULT_CORS_ORIGINS, Settings

ENV_NAMES = [
    "FAKE_MODEL",
    "ANTHROPIC_API_KEY",
    "LIVE_ACCESS_CODE",
    "CORS_ORIGINS",
    "RATE_LIMIT_PER_MINUTE",
    "DAILY_QUOTA",
    "PROJECT_ROOT",
]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_fake_mode_needs_no_secrets_and_has_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_MODEL", "1")
    settings = Settings()
    assert settings.fake_model is True
    assert settings.anthropic_api_key is None
    assert settings.live_access_code is None
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS
    assert settings.rate_limit_per_minute == 5
    assert settings.daily_quota == 50
    assert (settings.project_root / "pyproject.toml").is_file()


def test_live_mode_without_secrets_lists_both_names(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as caught:
        Settings()
    message = str(caught.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "LIVE_ACCESS_CODE" in message


def test_live_mode_lists_the_missing_name_but_never_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    with pytest.raises(ValidationError) as caught:
        Settings()
    message = str(caught.value)
    assert "LIVE_ACCESS_CODE" in message
    assert "ANTHROPIC_API_KEY" not in message
    assert "sk-secret-value" not in message


def test_live_mode_with_every_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("LIVE_ACCESS_CODE", "c")
    settings = Settings()
    assert settings.fake_model is False
    assert isinstance(settings.anthropic_api_key, SecretStr)
    assert isinstance(settings.live_access_code, SecretStr)
    assert "c" not in repr(settings.live_access_code).replace("SecretStr", "")


def test_cors_origins_come_from_a_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_MODEL", "true")
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example,,")
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]


def test_cors_origins_accept_a_list_and_numbers_and_paths_are_typed() -> None:
    settings = Settings(
        fake_model=True,
        cors_origins=["https://c.example"],
        rate_limit_per_minute=2,
        daily_quota=3,
        project_root=Path("somewhere"),
    )
    assert settings.cors_origins == ["https://c.example"]
    assert (settings.rate_limit_per_minute, settings.daily_quota) == (2, 3)
    assert settings.project_root == Path("somewhere")
