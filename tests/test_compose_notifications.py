from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from polyfactory.factories import DataclassFactory
from sqlalchemy.engine import Connection

import compose_notifications._utils.enrich
import compose_notifications._utils.notif_common
from _dependencies.commons import sqlalchemy_get_pool
from compose_notifications import main
from compose_notifications.main import LineInChangeLog
from tests.common import get_event_with_data
from tests.factories import db_models
from tests.factories.db_factories import ChangeLogFactory, UserFactory, get_session
from tests.factories.db_models import ChangeLog, User


class NotSentChangeLogFactory(ChangeLogFactory):
    notification_sent = None
    change_type = 0
    changed_field = 'new_search'


class LineInChageFactory(DataclassFactory[LineInChangeLog]):
    topic_type_id = 1
    forum_search_num = 1
    start_time = datetime.now()
    activities = [1, 2]
    managers = '["manager1","manager2"]'
    clickable_name = 'foo'


@pytest.fixture(autouse=True)
def local_patches():
    with (
        patch('compose_notifications.main.publish_to_pubsub'),
    ):
        yield


@pytest.fixture
def line_in_change_log() -> LineInChangeLog:
    return LineInChageFactory.build()


@pytest.fixture
def user_with_preferences() -> User:
    with get_session() as session:
        user = UserFactory.create_sync()
        #     user_pref_type_id - topic_type_id 0,3,4,5
        #     user_pref_search_whitelist, user_pref_search_filtering - ?? (no permissions)
        #     user_pref_region - region_id 1
        #     user_pref_radius - type None,  radius - kilometers

        # user_pref_age

        session.add_all(
            [
                # db_models.UserRegionalPreference(
                #     user_id=user.user_id, region_id=1, preference=1, created_at=datetime.now()
                # ),
                db_models.UserRegionalPreference(user_id=user.user_id, forum_folder_num=1),
                # db_models.User(user_id=user.user_id, region_id=1, preference=1, created_at=datetime.now()),
                db_models.UserPreference(user_id=user.user_id, pref_id=0, preference='new_searches'),
                db_models.UserPreference(user_id=user.user_id, pref_id=1, preference='status_changes'),
                db_models.UserPrefRegion(user_id=user.user_id, region_id=1),
                db_models.UserPrefRadiu(user_id=user.user_id, radius=1000),
                db_models.UserPrefTopicType(user_id=user.user_id, topic_type_id=0),
                db_models.UserPrefTopicType(user_id=user.user_id, topic_type_id=1),
                db_models.UserPrefTopicType(user_id=user.user_id, topic_type_id=30),
            ]
        )
        session.commit()
    return user


@pytest.fixture
def change_log_db_record() -> User:
    with get_session() as session:
        change_log_record = NotSentChangeLogFactory.create_sync(search_forum_num=1, change_type=1)
        session.add_all(
            [
                db_models.Search(
                    search_forum_num=1,
                    forum_folder_id=1,
                    topic_type_id=1,
                    status='НЖ',
                    forum_search_title='ЖИВ Иванов Иван Иванович, 33 года, г. Уфа, Республика Башкортостан',
                    family_name='Иванов',
                    age=83,
                    topic_type='search',
                    display_name='Иванов 33 года',
                    city_locations='[[54.683253050000005, 55.98561157727167]]',
                ),
            ]
        )
        if session.query(db_models.DictNotifType).filter(db_models.DictNotifType.type_id == 1).count() == 0:
            session.add_all(
                [
                    db_models.DictNotifType(type_id=1, type_name='new_search'),
                ]
            )

        session.commit()
    return change_log_record


@pytest.fixture
def connection() -> Connection:
    pool = sqlalchemy_get_pool(10, 10)
    with pool.connect() as conn:
        yield conn


def test_main(user_with_preferences: User, change_log_db_record):
    # NO SMOKE TEST compose_notifications.main.main
    # TODO paste something to change_log and users
    data = get_event_with_data({'foo': 1, 'triggered_by_func_id': '1'})
    # user = UserFactory.create_sync()

    main.main(data, 'context')
    assert True


def test_compose_users_list_from_users(user_with_preferences: User, connection: Connection):
    record = LineInChageFactory.build(forum_folder=1, change_type=0)
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
    compose_notifications._utils.enrich.enrich_new_record_with_emoji(line_in_change_log)
    assert line_in_change_log.topic_emoji
