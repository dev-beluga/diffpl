"""Runtime settings read from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DIFFPL_", extra="ignore")

    database_url: str = "postgresql+psycopg://diffpl:diffpl@localhost:5432/diffpl"
    mlflow_tracking_uri: str = "http://localhost:5000"
    seed: int = 42
    openai_api_key: str = ""  # platform.openai.com key (prepaid credits); never log or commit
    groq_api_key: str = ""  # console.groq.com key (free tier); never log or commit
    gemini_api_key: str = ""  # Google AI Studio key (free tier); never log or commit


def get_settings() -> Settings:
    return Settings()
