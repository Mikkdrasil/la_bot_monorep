import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from compose_notifications._utils.commons import ChangeType, LineInChangeLog, SearchFollowingMode, TopicType, User
from compose_notifications._utils.message_composer import MessageComposer
from compose_notifications._utils.notifications_maker import (
    NotificationMaker,
)
from compose_notifications._utils.users_list_composer import UserListFilter, check_if_age_requirements_met
from tests.factories import db_factories, db_models
from tests.test_compose_notifications.factories import LineInChangeLogFactory, UserFactory


class TestNotificationMaker:
    def test_generate_notifications_for_users(self, connection: Connection, dict_notif_type_status_change):
        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        user = UserFactory.build()
        composer = NotificationMaker(connection, record, [user])

        assert not record.processed
        composer.generate_notifications_for_users(1)
        assert record.processed

    def test_generate_notifications_for_user_text(
        self, connection: Connection, dict_notif_type_status_change, session: Session
    ):
        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        user = UserFactory.build()
        composer = NotificationMaker(connection, record, [user])
        mailing_id = composer.create_new_mailing_id()

        composer.generate_notification_for_user(mailing_id, user)

        query = session.query(db_models.NotifByUser).filter(
            db_models.NotifByUser.change_log_id == record.change_log_id,
            db_models.NotifByUser.user_id == user.user_id,
        )

        assert query.count() == 1
        notification: db_models.NotifByUser = query.first()
        assert notification.created
        assert notification.message_type == 'text'

    def test_generate_notifications_for_user_text_with_coords_1(
        self, connection: Connection, dict_notif_type_new, session: Session
    ):
        record = LineInChangeLogFactory.build(
            ignore=False,
            change_type=ChangeType.topic_new,
            topic_type_id=TopicType.search_regular,
            processed=False,
            search_latitude='60.0000',
            search_longitude='60.0000',
        )
        user = UserFactory.build(
            user_latitude='55.0000',
            user_longitude='55.0000',
        )
        composer = NotificationMaker(connection, record, [user])
        mailing_id = composer.create_new_mailing_id()

        composer.generate_notification_for_user(mailing_id, user)

        query = session.query(db_models.NotifByUser).filter(
            db_models.NotifByUser.change_log_id == record.change_log_id,
            db_models.NotifByUser.user_id == user.user_id,
        )

        assert query.count() == 2
        assert query.filter(db_models.NotifByUser.message_type == 'text').count() == 1
        assert query.filter(db_models.NotifByUser.message_type == 'coords').count() == 1

    def test_generate_notifications_for_user_text_with_coords_2(
        self, connection: Connection, dict_notif_type_first_post_change, session: Session
    ):
        record = LineInChangeLogFactory.build(
            ignore=False,
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            processed=False,
            search_latitude='60.0000',
            search_longitude='60.0000',
            new_value="{'add':['56.1234 60.1234']}",
        )
        user = UserFactory.build(
            user_latitude='55.0000',
            user_longitude='55.0000',
        )
        composer = NotificationMaker(connection, record, [user])
        mailing_id = composer.create_new_mailing_id()

        composer.generate_notification_for_user(mailing_id, user)

        query = session.query(db_models.NotifByUser).filter(
            db_models.NotifByUser.change_log_id == record.change_log_id,
            db_models.NotifByUser.user_id == user.user_id,
        )

        assert query.count() == 2
        assert query.filter(db_models.NotifByUser.message_type == 'text').count() == 1
        assert query.filter(db_models.NotifByUser.message_type == 'coords').count() == 1
