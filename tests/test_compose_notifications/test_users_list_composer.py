from sqlalchemy.engine import Connection

from compose_notifications._utils.users_list_composer import UsersListComposer
from tests.factories import db_models
from tests.test_compose_notifications.test_change_log import LineInChageFactory


def test_compose_users_list_from_users(user_with_preferences: db_models.User, connection: Connection):
    record = LineInChageFactory.build(forum_folder=1, change_type=0)

    users_list_composer = UsersListComposer(connection)
    res = users_list_composer.get_users_list_for_line_in_change_log(record)
    assert res
