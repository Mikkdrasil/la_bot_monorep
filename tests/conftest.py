import io
import os
import urllib.request
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import psycopg2
import pytest
import sqlalchemy
from dotenv import load_dotenv
from google.cloud import secretmanager
from psycopg2 import connect as psycopg2_connect_original
from sqlalchemy import create_engine as create_engine_original

from tests.common import get_config

USE_REAL_DB = True

load_dotenv()


@pytest.fixture(scope='session', autouse=True)
def create_test_db():
    """
    Automatically recreate test database schema for using in tests
    Be careful: all data in database would be deleted!
    """
    if not USE_REAL_DB:
        return

    from tests.tools import init_testing_db

    init_testing_db.main()


@pytest.fixture(autouse=True)
def patch_psycopg2_connection(create_test_db):
    """Connect to local DB"""

    def psycopg2_connection_wrapped(*args, **kwargs):
        config = get_config()

        return psycopg2_connect_original(
            host=config.pg_host,
            port=config.pg_port,
            dbname=config.cloud_postgres_db_name,
            user=config.cloud_postgres_username,
            password=config.cloud_postgres_password,
        )

    mocked_connection = psycopg2_connection_wrapped if USE_REAL_DB else MagicMock()
    with patch.object(psycopg2, 'connect', mocked_connection):
        yield


@pytest.fixture(autouse=True)
def patch_sqlalchemy_connection_url(create_test_db):
    """Connect to local DB"""

    def sqlalchemy_conn_url_wrapped(*args, **kwargs):
        config = get_config()

        url = sqlalchemy.engine.url.URL(
            'postgresql+pg8000',
            host=config.pg_host,
            port=config.pg_port,
            database=config.cloud_postgres_db_name,
            username=config.cloud_postgres_username,
            password=config.cloud_postgres_password,
        )

        return create_engine_original(url)

    mocked_connection = sqlalchemy_conn_url_wrapped if USE_REAL_DB else MagicMock()
    with patch.object(sqlalchemy, 'create_engine', mocked_connection):
        yield


def mock_access_secret_version(self, name: str):
    """
    patch for SecretManagerServiceClient.access_secret_version
    name: str, for example: f'projects/{project_id}/secrets/{secret_request}/versions/latest'
    """

    class SecretPayload(NamedTuple):
        data: bytes

    class SecretResponse(NamedTuple):
        payload: SecretPayload

    env_var_name = name.split('/')[3].upper().replace('-', '_')

    value = os.getenv(env_var_name)
    if value is None:
        raise ValueError(f'Environment variable {env_var_name} is not set')

    return SecretResponse(SecretPayload(data=value.encode()))


@pytest.fixture(autouse=True)
def patch_get_secrets():
    with (
        patch.object(secretmanager.SecretManagerServiceClient, 'access_secret_version', mock_access_secret_version),
        patch.object(secretmanager.SecretManagerServiceClient, '__init__', MagicMock(return_value=None)),
    ):
        yield


@pytest.fixture(autouse=True)
def patch_logging():
    """
    To disable for specific tests, use next advice:
    https://stackoverflow.com/questions/38748257/disable-autouse-fixtures-on-specific-pytest-marks

    """

    with patch('google.cloud.logging.Client') as mock:
        yield mock


@pytest.fixture(autouse=True)
def common_patches():
    """
    Common patch for all tests to enable imports
    """
    with (
        patch.object(urllib.request, 'urlopen') as urllib_request_mock,
        patch('google.cloud.pubsub_v1.PublisherClient'),
    ):
        urllib_request_mock.return_value = io.BytesIO(b'1')
        yield
