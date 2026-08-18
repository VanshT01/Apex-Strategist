from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Apex Strategist API"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./apex_strategist.db"
    fastf1_cache_dir: Path = Path("./data/fastf1")
    cors_origins: list[str] = ["http://localhost:3001"]
    model_path: Path = Path("./data/models")
    default_simulation_count: int = 1000
    max_simulation_count: int = 10000
    openf1_base_url: str = "https://api.openf1.org/v1"
    jolpica_base_url: str = "https://api.jolpi.ca/ergast/f1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
