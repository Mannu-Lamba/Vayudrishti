from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    MONGODB_URI: str

    MONGODB_CYCLONE_DATABASE: str = "cyclone_database"
    MONGODB_APP_DATABASE: str = "vayudrishti_local"

    FRONTEND_URL: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",  # absolute, so it works whichever directory uvicorn starts in
        extra="ignore",
    )


settings = Settings()