from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: str

    # worldcup26.ir API (free, no key required for read access)
    worldcup_api_url: str = "https://worldcup26.ir"
    # JWT lasts 84 days. Pre-populate via `POST /auth/authenticate` or set
    # email + password to enable automatic login on first sync.
    worldcup_api_token: str = ""
    worldcup_api_email: str = ""
    worldcup_api_password: str = ""

    # Auth
    secret_key: str = "change-me"
    admin_token: str = "admin"

    # Cron
    cron_token: str = "cron"


@lru_cache
def get_settings() -> Settings:
    return Settings()
