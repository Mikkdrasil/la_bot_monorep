import pytest

from compose_notifications._utils.notif_common import ChangeType, LineInChangeLog, SearchFollowingMode, User
from compose_notifications._utils.notifications_maker import (
    MessageComposer,
    NotificationComposer,
    UserListFilter,
    check_if_age_requirements_met,
)
from tests.factories import db_factories, db_models
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
    def test_filter_inforg_double_notification_for_users_1(self, connection):
        line_in_change_log = LineInChangeLogFactory.build(change_type=ChangeType.all)
        user = UserFactory.build()

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_inforg_double_notification_for_users()

        assert user in cropped_users

    def test_filter_inforg_double_notification_for_users_2(self, connection):
        line_in_change_log = LineInChangeLogFactory.build(change_type=ChangeType.topic_inforg_comment_new)
        user = UserFactory.build(all_notifs=True)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_inforg_double_notification_for_users()

        assert user not in cropped_users

    def test_filter_inforg_double_notification_for_users_3(self, connection):
        line_in_change_log = LineInChangeLogFactory.build(change_type=ChangeType.topic_inforg_comment_new)
        user = UserFactory.build(all_notifs=False)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_inforg_double_notification_for_users()

        assert user in cropped_users

    def test_filter_users_by_age_settings_1(self, connection):
        line_in_change_log = LineInChangeLogFactory.build(age_min=10, age_max=20)
        user = UserFactory.build(age_periods=[(19, 20)])

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_by_age_settings()

        assert user in cropped_users

    def test_filter_users_by_age_settings_2(self, connection):
        line_in_change_log = LineInChangeLogFactory.build(age_min=10, age_max=20)
        user = UserFactory.build(age_periods=[(21, 22)])

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_by_age_settings()

        assert user not in cropped_users

    def test_filter_users_by_search_radius_1(self, connection):
        line_in_change_log = LineInChangeLogFactory.build(
            city_locations='[[54.1234, 55.1234]]', search_latitude='', search_longitude=''
        )
        user = UserFactory.build(user_latitude='54.0000', user_longitude='55.0000', radius=100)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_by_search_radius()

        assert user in cropped_users

    def test_filter_users_by_search_radius_2(self, connection):
        line_in_change_log = LineInChangeLogFactory.build(
            city_locations='', search_latitude='54.1234', search_longitude='55.1234'
        )
        user = UserFactory.build(user_latitude='54.0000', user_longitude='55.0000', radius=100)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_by_search_radius()

        assert user in cropped_users

    def test_filter_users_by_search_radius_3(self, connection):
        line_in_change_log = LineInChangeLogFactory.build(
            city_locations='[[54.1234, 55.1234]]',
        )
        user = UserFactory.build(user_latitude='60.0000', user_longitude='60.0000', radius=1)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_by_search_radius()

        assert user not in cropped_users

    def test_filter_users_with_prepared_messages_1(self, connection):
        line_in_change_log = LineInChangeLogFactory.build()
        user = UserFactory.build()

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_with_prepared_messages()

        assert user in cropped_users

    def test_filter_users_with_prepared_messages_2(self, connection, default_dict_notif_type):
        line_in_change_log = LineInChangeLogFactory.build()
        user = UserFactory.build()
        user_model = db_factories.UserFactory.create_sync(user_id=user.user_id)
        mailing = db_factories.NotifMailingFactory.create_sync(dict_notif_type=default_dict_notif_type)
        db_factories.NotifByUserFactory.create_sync(
            user_id=user.user_id, change_log_id=line_in_change_log.change_log_id, mailing=mailing
        )

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_with_prepared_messages()

        assert user not in cropped_users

    def test_filter_users_not_following_this_search_1(self, connection, default_dict_notif_type):
        line_in_change_log = LineInChangeLogFactory.build()
        user = UserFactory.build()
        db_factories.UserFactory.create_sync(user_id=user.user_id)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_not_following_this_search()

        assert user in cropped_users

    def test_filter_users_not_following_this_search_2(self, connection, default_dict_notif_type):
        line_in_change_log = LineInChangeLogFactory.build()
        user = UserFactory.build()
        db_factories.UserFactory.create_sync(user_id=user.user_id)
        db_factories.UserPrefSearchFilteringFactory.create_sync(user_id=user.user_id, filter_name=['whitelist'])
        db_factories.UserPrefSearchWhitelistFactory.create_sync(
            user_id=user.user_id,
            search_id=line_in_change_log.forum_search_num,
            search_following_mode=SearchFollowingMode.ON,
        )

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_not_following_this_search()

        assert user in cropped_users

    def test_filter_users_not_following_this_search_3(self, connection, default_dict_notif_type):
        line_in_change_log = LineInChangeLogFactory.build()
        user = UserFactory.build()
        user_model = db_factories.UserFactory.create_sync(user_id=user.user_id)
        db_factories.UserPrefSearchFilteringFactory.create_sync(user_id=user.user_id, filter_name=['whitelist'])
        db_factories.UserPrefSearchWhitelistFactory.create_sync(
            user=user_model,
            search_id=line_in_change_log.forum_search_num,
            search_following_mode=SearchFollowingMode.OFF,
        )

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_not_following_this_search()

        assert user not in cropped_users

    def test_filter_users_not_following_this_search_4(self, connection, default_dict_notif_type):
        line_in_change_log = LineInChangeLogFactory.build()
        user = UserFactory.build()
        user_model = db_factories.UserFactory.create_sync(user_id=user.user_id)
        active_search = db_factories.SearchFactory.create_sync(status='NOT СТОП')
        db_factories.UserPrefSearchFilteringFactory.create_sync(user_id=user.user_id, filter_name=['whitelist'])
        db_factories.UserPrefSearchWhitelistFactory.create_sync(
            user=user_model,
            search_id=active_search.search_forum_num,
            search_following_mode=SearchFollowingMode.ON,
        )

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_not_following_this_search()

        assert user not in cropped_users

    def test_filter_users_not_following_this_search_5(self, connection, default_dict_notif_type):
        line_in_change_log = LineInChangeLogFactory.build()
        user = UserFactory.build()
        user_model = db_factories.UserFactory.create_sync(user_id=user.user_id)
        stopped_search = db_factories.SearchFactory.create_sync(status='СТОП')
        db_factories.UserPrefSearchFilteringFactory.create_sync(user_id=user.user_id, filter_name=['whitelist'])
        db_factories.UserPrefSearchWhitelistFactory.create_sync(
            user=user_model,
            search_id=stopped_search.search_forum_num,
            search_following_mode=SearchFollowingMode.ON,
        )

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_not_following_this_search()

        assert user in cropped_users

    def test_filter_apply_1(self, connection, default_dict_notif_type):
        # complex filter
        line_in_change_log = LineInChangeLogFactory.build(
            city_locations='', search_latitude='54.1234', search_longitude='55.1234'
        )
        user = UserFactory.build(user_latitude='', user_longitude='', radius=0, age_periods=[])
        user_model = db_factories.UserFactory.create_sync(user_id=user.user_id)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer.apply()

        assert user in cropped_users

    def test_filter_apply_2(self, connection, default_dict_notif_type):
        # complex filter
        line_in_change_log = LineInChangeLogFactory.build(
            city_locations='', search_latitude='60.1234', search_longitude='60.1234'
        )
        user = UserFactory.build(user_latitude='54.0000', user_longitude='55.0000', radius=1, age_periods=[])
        user_model = db_factories.UserFactory.create_sync(user_id=user.user_id)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer.apply()

        assert user not in cropped_users
