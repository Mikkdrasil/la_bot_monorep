from unittest.mock import patch

from telegram import Bot
from telegram.ext import ExtBot

from tests.common import get_event_with_data


def test_main():
    from manage_topics.main import main

    event = get_event_with_data(
        {
            'topic_id': 123,
            'visibility': True,
            'status': 'on',
        }
    )

    with (
        patch.object(ExtBot, 'send_message'),
        patch.object(Bot, 'get_me'),
    ):
        main(event, 'context')
        assert True
        # TODO assert that event was published
        # TODO check record in table `change_log`
