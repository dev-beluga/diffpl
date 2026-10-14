"""Runtime settings read from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DIFFPL_", extra="ignore")

    database_url: str = "postgresql+psycopg://diffpl:diffpl@localhost:5432/diffpl"
    mlflow_tracking_uri: str = "http://localhost:5000"
    seed: int = 42


def get_settings() -> Settings:
    return Settings()
