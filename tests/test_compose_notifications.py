from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# from tests.factories.db_models import ChangeLog, User
from faker import Faker
from polyfactory.factories import DataclassFactory
from sqlalchemy.engine import Connection

import compose_notifications._utils.enrich
import compose_notifications._utils.notif_common
from _dependencies.commons import sqlalchemy_get_pool
from compose_notifications import main
from compose_notifications.main import LineInChangeLog
from tests.common import get_event_with_data
from tests.factories import db_models
from tests.factories.db_factories import ChangeLogFactory, SearchFactory, UserFactory, get_session

faker = Faker('ru_RU')


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
def user_with_preferences() -> db_models.User:
    with get_session() as session:
        user = UserFactory.create_sync()
        session.add_all(
            [
                db_models.UserRegionalPreference(user_id=user.user_id, forum_folder_num=1),
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
def default_dict_notif_type() -> db_models.DictNotifType:
    with get_session() as session:
        if session.query(db_models.DictNotifType).filter(db_models.DictNotifType.type_id == 1).count() == 0:
            session.add(db_models.DictNotifType(type_id=1, type_name='new_search'))
        session.commit()


@pytest.fixture
def search_record(default_dict_notif_type: db_models.DictNotifType) -> db_models.Search:
    family = faker.last_name()
    return SearchFactory.create_sync(
        search_forum_num=faker.random_int(min=1, max=10000000),
        status='НЖ',
        forum_search_title=f'ЖИВ {family} Иван Иванович, 33 года, г. Уфа, Республика Башкортостан',
        family_name='Иванов',
        topic_type_id=1,
        topic_type='search',
        display_name=f'{family} 33 года',
        city_locations='[[54.683253050000005, 55.98561157727167]]',
    )


@pytest.fixture
def change_log_db_record(search_record: db_models.Search) -> db_models.ChangeLog:
    return NotSentChangeLogFactory.create_sync(search_forum_num=search_record.search_forum_num, change_type=1)


@pytest.fixture
def connection() -> Connection:
    pool = sqlalchemy_get_pool(10, 10)
    with pool.connect() as conn:
        yield conn


def test_main(
    user_with_preferences: db_models.User,
    change_log_db_record: db_models.ChangeLog,
    search_record: db_models.Search,
):
    # NO SMOKE TEST compose_notifications.main.main
    # TODO paste something to change_log and users
    data = get_event_with_data({'foo': 1, 'triggered_by_func_id': '1'})
    # user = UserFactory.create_sync()

    main.main(data, 'context')
    """
    TODO assert that records in notif_by_user appeared
    """
    assert True


def test_compose_users_list_from_users(user_with_preferences: db_models.User, connection: Connection):
    record = LineInChageFactory.build(forum_folder=1, change_type=0)
    res = main.compose_users_list_from_users(connection, record)
    assert res


def test_compose_com_msg_on_new_topic(line_in_change_log: compose_notifications._utils.notif_common.LineInChangeLog):
    # NO SMOKE TEST compose_notifications.main.compose_com_msg_on_new_topic
    compose_notifications._utils.enrich.compose_com_msg_on_new_topic(line_in_change_log)
    assert 'manager1' in line_in_change_log.managers and 'manager2' in line_in_change_log.managers


def test_enrich_new_record_with_emoji(line_in_change_log: compose_notifications._utils.notif_common.LineInChangeLog):
    # NO SMOKE TEST compose_notifications.main.enrich_new_record_with_emoji
    compose_notifications._utils.enrich.enrich_new_record_with_emoji(line_in_change_log)
    assert line_in_change_log.topic_emoji


def test_get_change_log_record_any(connection: Connection, change_log_db_record: db_models.ChangeLog):
    """
    get one record in change_log and assert that it is enriched with other fields
    """
    record = main.select_first_record_from_change_log(connection)
    assert record


def test_get_change_log_record_by_id(
    connection: Connection, change_log_db_record: db_models.ChangeLog, search_record: db_models.Search
):
    record = main.select_first_record_from_change_log(connection, change_log_db_record.id)
    assert record.change_id == change_log_db_record.id
    assert record.changed_field == change_log_db_record.changed_field
    assert record.forum_search_num == change_log_db_record.search_forum_num

    assert record.title == search_record.forum_search_title
    assert record.city_locations == search_record.city_locations
