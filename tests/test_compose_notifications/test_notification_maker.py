import pytest
from sqlalchemy.engine import Connection

from compose_notifications._utils.notif_common import ChangeType, LineInChangeLog, SearchFollowingMode, User
from compose_notifications._utils.notifications_maker import (
    MessageComposer,
    NotificationMaker,
)
from compose_notifications._utils.users_list_composer import UserListFilter, check_if_age_requirements_met
from tests.factories import db_factories, db_models
from tests.test_compose_notifications.factories import LineInChangeLogFactory, UserFactory


class TestNotificationMaker:
    def test_1(self, connection: Connection, default_dict_notif_type):
        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        user = UserFactory.build()
        composer = NotificationMaker(connection)

        assert not record.processed
        composer.generate_notifications_for_users(record, [user], 1)
        assert record.processed

    def test_2(self, connection: Connection, default_dict_notif_type):
        record = LineInChangeLogFactory.build(ignore=False, change_type=ChangeType.topic_status_change, processed=False)
        user = UserFactory.build()
        composer = NotificationMaker(connection)

        mailing_id = composer.create_new_mailing_id(record)
        composer.generate_notification_for_user(record, mailing_id, user)
        # TODO assert what??
