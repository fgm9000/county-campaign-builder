"""Typed configuration read from the environment (pydantic-settings)."""

from pathlib import Path
from typing import Annotated, Any, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORS_ORIGINS = ["https://fgm9000.github.io"]
DEFAULT_RATE_LIMIT_PER_MINUTE = 5
DEFAULT_DAILY_QUOTA = 50


class Settings(BaseSettings):
    """Environment-driven settings; live mode requires the Anthropic key and the access code."""

    # Validation errors must never echo input values: they can be secrets read from the environment.
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    fake_model: bool = False
    anthropic_api_key: SecretStr | None = None
    live_access_code: SecretStr | None = None
    cors_origins: Annotated[list[str], NoDecode] = list(DEFAULT_CORS_ORIGINS)
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    daily_quota: int = DEFAULT_DAILY_QUOTA
    project_root: Path = DEFAULT_PROJECT_ROOT

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _live_mode_needs_secrets(self) -> Self:
        if self.fake_model:
            return self
        required = {
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "LIVE_ACCESS_CODE": self.live_access_code,
        }
        missing = [name for name, secret in required.items() if secret is None]
        if missing:
            raise ValueError(f"live mode requires: {', '.join(missing)}")
        return self
