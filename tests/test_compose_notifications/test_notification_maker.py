import pytest

from compose_notifications._utils.notifications_maker import (
    MessageComposer,
    NotificationComposer,
    UserListFilter,
    check_if_age_requirements_met,
)
from tests.test_compose_notifications.factories import LineInChangeLogFactory, UserFactory


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
    assert check_if_age_requirements_met(search_ages, user_ages) == equals


class TestUsersFilter:
    def test_1(self, connection):
        """
        input = LineInChangeLog + UsersList (1 user)
        output = cropped list of users (1 or 0 users).
        """
        line_in_change_log = LineInChangeLogFactory.build(
            # topic_type_id=1,
            # user_id=users_list[0].user_id,
            # message=["Test Message"],
        )
        users_list = UserFactory.batch(
            2,
        )
        filterer = UserListFilter(connection, line_in_change_log, users_list)
        cropped_users = filterer.apply()
        assert True


"""
How to test NotificationMaker class?

maybe split to 2 parts:
1. filtering users
2. preparing notifications

"""
