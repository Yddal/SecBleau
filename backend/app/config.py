from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database — must be set via DATABASE_URL environment variable
    database_url: str = "postgresql+asyncpg://localhost:5432/secbleau"

    # Netatmo (optional)
    netatmo_client_id: str = ""
    netatmo_client_secret: str = ""

    # App
    environment: str = "production"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Fontainebleau bounding box for weather + Netatmo queries
    bleau_lat_min: float = 48.20
    bleau_lat_max: float = 48.60
    bleau_lon_min: float = 2.40
    bleau_lon_max: float = 3.00

    # Model settings
    weather_history_days: int = 7       # Days of past weather used in moisture simulation
    weather_forecast_days: int = 2      # Days of forecast to fetch
    score_climbable_threshold: float = 0.70  # Fixed 70% threshold for yellow/green transition
    min_reports_for_full_opacity: int = 3    # Reports needed before boulder shows full opacity

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def netatmo_enabled(self) -> bool:
        return bool(self.netatmo_client_id and self.netatmo_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
