from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://metro:metro@db:5432/metro"
    hh_metro_api_url: str = "https://api.hh.ru/metro/1"
    # Время в пути (мок): минуты
    minutes_per_segment: float = 3.0   # перегон между двумя станциями
    minutes_per_transfer: float = 6.0  # переход
    admin_api_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
