import os
import re
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # APP_ENV_FILE="" отключает чтение .env (так делают тесты, чтобы локальные настройки на них не влияли)
    model_config = SettingsConfigDict(
        env_file=os.getenv("APP_ENV_FILE", ".env") or None,
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    # Если KEITARO_URL пуст или KEITARO_MOCK=true — работаем со встроенным фейковым Keitaro.
    keitaro_url: str = ""
    keitaro_api_key: str = ""
    keitaro_mock: bool = False
    keitaro_timeout: float = 30.0
    keitaro_timezone: str = "Europe/Moscow"

    # Что выбрано в форме создатора по умолчанию (ID в Keitaro)
    default_domain_id: int | None = None
    default_group_id: int | None = None
    default_traffic_source_id: int | None = None

    geo_redirect_url: str = "https://google.com"
    database_url: str = "sqlite+aiosqlite:///./testorator.db"

    @property
    def use_mock(self) -> bool:
        return self.keitaro_mock or not self.keitaro_url

    @property
    def tracker_url(self) -> str | None:
        """Корень трекера без /admin и /admin_api/v1, например https://tlgk.host. None в демо-режиме."""
        if self.use_mock:
            return None
        return re.sub(r"/(admin_api/v1|admin)/?$", "", self.keitaro_url.strip().rstrip("/"))

    @property
    def keitaro_admin_url(self) -> str | None:
        return f"{self.tracker_url}/admin/" if self.tracker_url else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
