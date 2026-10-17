from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reads ``CLOUDFLARE_ACCOUNT_ID``, ``CLOUDFLARE_API_TOKEN`` and ``CLEF_MODEL``
    from the environment or a local ``.env`` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cloudflare_account_id: str
    cloudflare_api_token: SecretStr
    clef_model: Literal["clef", "clef-flash"] = "clef-flash"
