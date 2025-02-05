from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from polyfactory.factories import DataclassFactory
from sqlalchemy.engine import Connection

import compose_notifications._utils.enrich
import compose_notifications._utils.notif_common
from _dependencies.commons import sqlalchemy_get_pool
from compose_notifications import main
from compose_notifications.main import LineInChangeLog
from tests.common import get_event_with_data
from tests.factories.db_factories import ChangeLogFactory, UserFactory
from tests.factories.db_models import ChangeLog, User


class NotSentChangeLogFactory(ChangeLogFactory):
    notification_sent = None


class LineInChageFactory(DataclassFactory[LineInChangeLog]):
    topic_type_id = 1
    forum_search_num = 1
    start_time = datetime.now()
    activities = [1, 2]
    managers = '["manager1","manager2"]'
    clickable_name = 'foo'


@pytest.fixture
def line_in_change_log() -> LineInChangeLog:
    return LineInChageFactory.build()


@pytest.fixture
def user_with_preferences() -> User:
    user = UserFactory.create_sync()
    return user


@pytest.fixture
def change_log_db_record() -> User:
    user = UserFactory.create_sync()
    return user


@pytest.fixture
def connection() -> Connection:
    pool = sqlalchemy_get_pool(10, 10)
    with pool.connect() as conn:
        yield conn


def test_main(user_with_preferences: User):
    # NO SMOKE TEST compose_notifications.main.main
    # TODO paste something to change_log and users
    data = get_event_with_data({'foo': 1, 'triggered_by_func_id': '1'})
    user = UserFactory.create_sync()
    change_log = NotSentChangeLogFactory.create_sync()

    main.main(data, 'context')
    assert True


def test_compose_users_list_from_users(user_with_preferences: User, connection: Connection):
    record = LineInChageFactory.build()
    res = main.compose_users_list_from_users(connection, record)
    assert res


def test_compose_com_msg_on_new_topic(line_in_change_log: compose_notifications._utils.notif_common.LineInChangeLog):
    # NO SMOKE TEST compose_notifications.main.compose_com_msg_on_new_topic
    messages, message, line_ignore = compose_notifications._utils.enrich.compose_com_msg_on_new_topic(
        line_in_change_log
    )
    assert 'manager1' in message.managers and 'manager2' in message.managers


def test_enrich_new_record_with_emoji(line_in_change_log: compose_notifications._utils.notif_common.LineInChangeLog):
    # NO SMOKE TEST compose_notifications.main.enrich_new_record_with_emoji
    res = compose_notifications._utils.enrich.enrich_new_record_with_emoji(line_in_change_log)
    assert res.topic_emoji
