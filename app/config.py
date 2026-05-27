from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    polytrad_master_key: str = "change-me"
    database_url: str = "sqlite+aiosqlite:///./polytrad.db"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24h
    admin_username: str = "admin"
    admin_password: str = "changeme123"
    polymarket_chain_id: int = 137
    polymarket_clob_host: str = "https://clob.polymarket.com"
    polymarket_gamma_host: str = "https://gamma-api.polymarket.com"
    polymarket_data_host: str = "https://data-api.polymarket.com"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
