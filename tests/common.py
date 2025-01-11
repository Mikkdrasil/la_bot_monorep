import base64
from functools import lru_cache

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    bot_api_token: str
    my_telegram_id: str

    cloud_postgres_username: str
    cloud_postgres_password: str
    cloud_postgres_db_name: str
    cloud_postgres_connection_name: str

    pg_host: str
    pg_port: int


@lru_cache
def get_config() -> Config:
    return Config()


def get_event_with_data(data) -> dict:
    encoded_data = base64.b64encode(str({'data': {'message': data}}).encode())
    event = {'data': encoded_data}
    return event
