from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# from tests.factories.db_models import ChangeLog, User
from faker import Faker
from polyfactory.factories import DataclassFactory
from sqlalchemy.engine import Connection

import compose_notifications._utils.log_record_composer
import compose_notifications._utils.notif_common
import compose_notifications._utils.users_list_composer
from _dependencies.commons import sqlalchemy_get_pool
from compose_notifications import main
from compose_notifications._utils.notif_common import ChangeType, TopicType, get_coords_from_list
from compose_notifications.main import LineInChangeLog
from tests.common import get_event_with_data
from tests.factories import db_factories, db_models

faker = Faker('ru_RU')


class NotSentChangeLogFactory(db_factories.ChangeLogFactory):
    notification_sent = None
    change_type = 0
    changed_field = 'new_search'


class LineInChageFactory(DataclassFactory[LineInChangeLog]):
    topic_type_id = TopicType.search_regular
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
    with db_factories.get_session() as session:
        user = db_factories.UserFactory.create_sync()
        session.add_all(
            [
                # db_models.UserRegionalPreference(user_id=user.user_id, forum_folder_num=1),
                # db_models.UserPreference(user_id=user.user_id, pref_id=0, preference='new_searches'),
                db_models.UserPreference(user_id=user.user_id, pref_id=ChangeType.all, preference='status_changes'),
                db_models.UserPrefRegion(user_id=user.user_id, region_id=1),
                db_models.UserPrefRadiu(user_id=user.user_id, radius=1000),
                db_models.UserPrefTopicType(user_id=user.user_id, topic_type_id=TopicType.all),
            ]
        )
        session.commit()
    return user


@pytest.fixture
def default_dict_notif_type() -> db_models.DictNotifType:
    with db_factories.get_session() as session:
        if session.query(db_models.DictNotifType).filter(db_models.DictNotifType.type_id == 1).count() == 0:
            session.add(db_models.DictNotifType(type_id=1, type_name='new_search'))
        session.commit()


@pytest.fixture
def search_record(default_dict_notif_type: db_models.DictNotifType) -> db_models.Search:
    family = faker.last_name()
    return db_factories.SearchFactory.create_sync(
        status='НЖ',
        forum_search_title=f'ЖИВ {family} Иван Иванович, 33 года, г. Уфа, Республика Башкортостан',
        family_name='Иванов',
        topic_type_id=TopicType.search_regular,
        display_name=f'{family} 33 года',
        city_locations='[[54.683253050000005, 55.98561157727167]]',
    )


@pytest.fixture
def change_log_db_record(search_record: db_models.Search) -> db_models.ChangeLog:
    return NotSentChangeLogFactory.create_sync(
        search_forum_num=search_record.search_forum_num, change_type=ChangeType.topic_status_change
    )


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

    users_list_composer = compose_notifications._utils.users_list_composer.UsersListComposer(connection)
    res = users_list_composer.get_users_list_for_line_in_change_log(record)
    assert res


# @pytest.mark.skip(reason='fix later')
def test_get_coords_from_list():
    messages = ['56.1234 60.5678']
    c1, c2 = get_coords_from_list(messages)
    assert c1, c2 == ('56.12340', '60.56780')


@pytest.mark.parametrize(
    'search_ages, user_ages, equals',
    [
        ([1, 2], [(1, 2)], True),
        ([1, 3], [(1, 2)], True),
        ([1, 2], [(2, 3)], True),
        ([3, 4], [(1, 2)], False),
        ([1, 2], [(3, 4)], False),
        ([3, 4], [(1, 2), (2, 3)], True),
        ([3, 4], [(1, 2), (5, 6)], False),
        ([], [], True),
        ([None, None], [], True),
    ],
)
def test_age_requirements_check(search_ages, user_ages, equals):
    from compose_notifications._utils.notifications_maker import check_if_age_requirements_met

    assert check_if_age_requirements_met(search_ages, user_ages) == equals


def test_define_dist_and_dir_to_search():
    from compose_notifications._utils.notifications_maker import define_dist_and_dir_to_search

    dist, direction = define_dist_and_dir_to_search('56.1234', '60.56780', '55.1234', '60.56780')
    assert dist == 111.2


class TestChangeLogExtractor:
    def test_get_change_log_record_any(self, connection: Connection, change_log_db_record: db_models.ChangeLog):
        """
        get one record in change_log and assert that it is enriched with other fields
        """
        record = main.LogRecordExtractor(conn=connection).get_line()
        assert record

    def test_get_change_log_record_by_id(
        self, connection: Connection, change_log_db_record: db_models.ChangeLog, search_record: db_models.Search
    ):
        record = main.LogRecordExtractor(conn=connection, record_id=change_log_db_record.id).get_line()
        assert record.change_log_id == change_log_db_record.id
        assert record.changed_field == change_log_db_record.changed_field
        assert record.forum_search_num == change_log_db_record.search_forum_num

        assert record.title == search_record.forum_search_title
        assert record.city_locations == search_record.city_locations

    def test_get_change_log_record_with_managers(
        self, connection: Connection, change_log_db_record: db_models.ChangeLog, search_record: db_models.Search
    ):
        managers_record = db_factories.SearchAttributeFactory.create_sync(
            search_forum_num=search_record.search_forum_num, attribute_name='managers'
        )
        record = main.LogRecordExtractor(conn=connection, record_id=change_log_db_record.id).get_line()
        assert record.managers == managers_record.attribute_value

    def test_get_change_log_record_with_search_activity(
        self, connection: Connection, change_log_db_record: db_models.ChangeLog, search_record: db_models.Search
    ):
        dict_activity_record = db_factories.DictSearchActivityFactory.create_sync()
        search_activity_record = db_factories.SearchActivityFactory.create_sync(
            search_forum_num=search_record.search_forum_num, activity_type=dict_activity_record.activity_id
        )
        # TODO create 2 activities and 2
        record = main.LogRecordExtractor(conn=connection, record_id=change_log_db_record.id).get_line()
        assert record.activities == [dict_activity_record.activity_name]
