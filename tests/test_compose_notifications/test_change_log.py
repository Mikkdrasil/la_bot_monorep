from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# from tests.factories.db_models import ChangeLog, User
from faker import Faker
from sqlalchemy.engine import Connection

from compose_notifications import main
from compose_notifications._utils.commons import ChangeType, TopicType
from compose_notifications.main import LineInChangeLog
from tests.common import get_event_with_data
from tests.factories import db_factories, db_models
from tests.test_compose_notifications.factories import LineInChangeLogFactory

faker = Faker('ru_RU')


class NotSentChangeLogFactory(db_factories.ChangeLogFactory):
    notification_sent = None
    change_type = 0
    changed_field = 'new_search'


@pytest.fixture
def line_in_change_log() -> LineInChangeLog:
    return LineInChangeLogFactory.build()


@pytest.fixture
def search_record(dict_notif_type_status_change: db_models.DictNotifType) -> db_models.Search:
    family = faker.last_name()
    return db_factories.SearchFactory.create_sync(
        status='НЖ',
        forum_search_title=f'ЖИВ {family} Иван Иванович, 33 года, г. Уфа, Республика Башкортостан',
        family_name='Иванов',
        topic_type_id=TopicType.search_regular,
        display_name=f'{family} 33 года',
        city_locations='[[54.683253050000005, 55.98561157727167]]',
        search_start_time=datetime.now() - timedelta(days=1),
    )


@pytest.fixture
def change_log_db_record_status_change(search_record: db_models.Search) -> db_models.ChangeLog:
    return NotSentChangeLogFactory.create_sync(
        search_forum_num=search_record.search_forum_num, change_type=ChangeType.topic_status_change
    )


@pytest.fixture
def change_log_db_record_topic_new(search_record: db_models.Search) -> db_models.ChangeLog:
    return NotSentChangeLogFactory.create_sync(
        search_forum_num=search_record.search_forum_num, change_type=ChangeType.topic_new
    )


@pytest.fixture
def change_log_db_record_topic_comment_new(search_record: db_models.Search) -> db_models.ChangeLog:
    return NotSentChangeLogFactory.create_sync(
        search_forum_num=search_record.search_forum_num, change_type=ChangeType.topic_comment_new
    )


@pytest.fixture
def comment(change_log_db_record_topic_comment_new: db_models.ChangeLog) -> db_models.Comment:
    return db_factories.CommentFactory.create_sync(
        search_forum_num=change_log_db_record_topic_comment_new.search_forum_num, notification_sent=None
    )


def test_main_entrypoint(
    change_log_db_record_status_change: db_models.ChangeLog,
    search_record: db_models.Search,
):
    # NO SMOKE TEST compose_notifications.main.main
    data = get_event_with_data({'foo': 1, 'triggered_by_func_id': '1'})
    main.main(data, 'context')


class TestChangeLogExtractor:
    def test_get_change_log_record_any(
        self, connection: Connection, change_log_db_record_status_change: db_models.ChangeLog
    ):
        """
        get one record in change_log and assert that it is enriched with other fields
        """
        record = main.LogRecordComposer(conn=connection).get_line()
        assert record

    def test_get_change_log_record_by_id(
        self,
        connection: Connection,
        change_log_db_record_status_change: db_models.ChangeLog,
        search_record: db_models.Search,
    ):
        record = main.LogRecordComposer(conn=connection, record_id=change_log_db_record_status_change.id).get_line()
        assert record.change_log_id == change_log_db_record_status_change.id
        assert record.changed_field == change_log_db_record_status_change.changed_field
        assert record.forum_search_num == change_log_db_record_status_change.search_forum_num

        assert record.title == search_record.forum_search_title
        assert record.city_locations == search_record.city_locations

    def test_get_change_log_record_with_managers(
        self,
        connection: Connection,
        change_log_db_record_status_change: db_models.ChangeLog,
        search_record: db_models.Search,
    ):
        managers_record = db_factories.SearchAttributeFactory.create_sync(
            search_forum_num=search_record.search_forum_num, attribute_name='managers'
        )
        record = main.LogRecordComposer(conn=connection, record_id=change_log_db_record_status_change.id).get_line()
        assert record.managers == managers_record.attribute_value

    def test_get_change_log_record_with_search_activity(
        self,
        connection: Connection,
        change_log_db_record_status_change: db_models.ChangeLog,
        search_record: db_models.Search,
    ):
        dict_activity_record = db_factories.DictSearchActivityFactory.create_sync()
        search_activity_record = db_factories.SearchActivityFactory.create_sync(
            search_forum_num=search_record.search_forum_num, activity_type=dict_activity_record.activity_id
        )
        record = main.LogRecordComposer(conn=connection, record_id=change_log_db_record_status_change.id).get_line()
        assert record.activities == [dict_activity_record.activity_name]

    def test_get_change_log_record_with_search_activity_and_comments(
        self,
        connection: Connection,
        change_log_db_record_topic_comment_new: db_models.ChangeLog,
        search_record: db_models.Search,
        comment: db_models.Comment,
    ):
        dict_activity_record = db_factories.DictSearchActivityFactory.create_sync()
        search_activity_record = db_factories.SearchActivityFactory.create_sync(
            search_forum_num=search_record.search_forum_num, activity_type=dict_activity_record.activity_id
        )
        record = main.LogRecordComposer(conn=connection, record_id=change_log_db_record_topic_comment_new.id).get_line()
        assert record.activities == [dict_activity_record.activity_name]
        assert len(record.comments) == 1
        assert record.comments[0].text == comment.comment_text
        # TODO inforg comment
