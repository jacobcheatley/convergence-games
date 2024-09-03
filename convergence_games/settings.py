from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    DEBUG: bool = False
    DATABASE_PATH: str = "database.db"
    RECREATE_DATABASE: bool = False
    USE_HTTPS: bool = False
    INITIALISE_DATA: bool = True
    FLAG_SCHEDULE: bool = False
    FLAG_USERS: bool = False
    FLAG_ALWAYS_ALLOW_CHECKINS: bool = False
    API_KEY: str = "api-key"
    DATABASE_USERNAME: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_HOST: str = ""
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = ""
    ENABLE_APP_INSIGHTS: bool = False
    ENABLE_SENTRY: bool = True
    SENTRY_DSN: str = ""
    ENVIRONMENT_NAME: str = "development"


SETTINGS = Settings()
