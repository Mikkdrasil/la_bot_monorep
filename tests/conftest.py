import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Bot
from telegram.ext import ExtBot

from _dependencies.commons import Topics
from tests.common import get_test_config, topic_to_receiver_function

ENABLE_TYPE_COLLECTION = True


@pytest.fixture(autouse=True, scope='session')
def collect_types_fixture():
    if not ENABLE_TYPE_COLLECTION:
        yield
        return
    from pyannotate_runtime import collect_types

    collect_types.init_types_collection()
    with collect_types.collect():
        yield
    collect_types.dump_stats('type_info.json')


@pytest.fixture(autouse=True, scope='session')
def patch_app_config(collect_types_fixture):
    """Connect to local DB"""

    with patch('_dependencies.commons._get_config', get_test_config):
        yield


@pytest.fixture(autouse=True)
def patch_publish_topic():
    def patched_send_topic(topic_name: Topics, topic_path, data: dict) -> None:
        receiver = topic_to_receiver_function(topic_name)
        receiver({'data': base64.encodebytes(data)}, 'context')

    with patch('_dependencies.commons._send_topic', patched_send_topic):
        yield


@pytest.fixture(autouse=True)
def patch_http():
    with (
        patch('urllib.request'),
        patch('requests.get'),
        patch('requests.post'),
        patch('requests.session'),
        patch('requests.Session'),
        patch('google.auth.transport.requests.Request'),
        patch('google.auth.default'),
        patch('google.oauth2.id_token.fetch_id_token'),
    ):
        yield


@pytest.fixture(autouse=True)
def patch_pubsub_client() -> MagicMock:
    with patch('google.cloud.pubsub_v1.PublisherClient', MagicMock()) as mock:
        yield mock


@pytest.fixture(autouse=True)
def bot_mock_send_message() -> AsyncMock:
    # TODO get list of sent messages
    with (
        patch.object(Bot, 'get_me'),
        patch.object(ExtBot, 'send_message') as mock_send_message,
    ):
        yield mock_send_message
