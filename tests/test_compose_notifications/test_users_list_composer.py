import pytest
from sqlalchemy.engine import Connection

from compose_notifications._utils.commons import ChangeType, LineInChangeLog, SearchFollowingMode, TopicType, User
from compose_notifications._utils.message_composer import MessageComposer
from compose_notifications._utils.notifications_maker import (
    NotificationMaker,
)
from compose_notifications._utils.users_list_composer import (
    UserListFilter,
    UsersListComposer,
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


def create_user_with_preferences(
    pref_ids: list[int] = [],
    region_ids: list[int] = [],
    topic_type_ids: list[int] = [],
    forum_folder_ids: list[int] = [],
    user_coordinates: tuple[str, str] | None = None,
    age_periods: list[tuple[int, int]] = [],
    radius: int | None = None,
) -> db_models.User:
    user = db_factories.UserFactory.create_sync()

    for pref_id in pref_ids:
        db_factories.UserPreferenceFactory.create_sync(user_id=user.user_id, pref_id=pref_id)

    for region_id in region_ids:
        db_factories.UserPrefRegionFactory.create_sync(user_id=user.user_id, region_id=region_id)

    for topic_type_id in topic_type_ids:
        db_factories.UserPrefTopicTypeFactory.create_sync(user_id=user.user_id, topic_type_id=topic_type_id)

    for forum_folder_id in forum_folder_ids:
        db_factories.UserRegionalPreferenceFactory.create_sync(user_id=user.user_id, forum_folder_num=forum_folder_id)

    if user_coordinates is not None:
        db_factories.UserCoordinateFactory.create_sync(
            user_id=user.user_id, latitude=user_coordinates[0], longitude=user_coordinates[1]
        )

    for age_period in age_periods:
        db_factories.UserPrefAgeFactory.create_sync(
            user_id=user.user_id, period_min=age_period[0], period_max=age_period[1]
        )

    if radius is not None:
        db_factories.UserPrefRadiusFactory.create_sync(user_id=user.user_id, radius=radius)

    return user


class TestUsersListComposer:
    def test_all_change_types(self, connection: Connection):
        record = LineInChangeLogFactory.build(change_type=ChangeType.topic_first_post_change)

        user = create_user_with_preferences(
            pref_ids=[ChangeType.all],
            region_ids=[1],
            topic_type_ids=[record.topic_type_id],
            forum_folder_ids=[record.forum_folder],
        )

        users_list_composer = UsersListComposer(connection)
        res = users_list_composer.get_users_list_for_line_in_change_log(record)
        assert len(res) == 1
        first_user = res[0]
        assert first_user.user_id == user.user_id
        assert first_user.all_notifs is True
        assert not first_user.user_new_search_notifs
        assert first_user.radius == 0
        assert not first_user.user_latitude
        assert not first_user.user_longitude

    def test_one_change_type(self, connection: Connection):
        record = LineInChangeLogFactory.build(change_type=ChangeType.topic_first_post_change)

        user = create_user_with_preferences(
            pref_ids=[record.change_type],
            region_ids=[1],
            topic_type_ids=[record.topic_type_id],
            forum_folder_ids=[record.forum_folder],
        )

        users_list_composer = UsersListComposer(connection)
        res = users_list_composer.get_users_list_for_line_in_change_log(record)
        assert len(res) == 1
        first_user = res[0]
        assert first_user.user_id == user.user_id
        assert first_user.all_notifs is False

    def test_another_change_type(self, connection: Connection):
        record = LineInChangeLogFactory.build(change_type=ChangeType.topic_first_post_change)

        user = create_user_with_preferences(
            pref_ids=[ChangeType.bot_news],
            region_ids=[1],
            topic_type_ids=[record.topic_type_id],
            forum_folder_ids=[record.forum_folder],
        )

        users_list_composer = UsersListComposer(connection)
        res = users_list_composer.get_users_list_for_line_in_change_log(record)
        assert not res

    def test_radius(self, connection: Connection):
        record = LineInChangeLogFactory.build(change_type=ChangeType.topic_first_post_change)

        user = create_user_with_preferences(
            pref_ids=[record.change_type],
            region_ids=[1],
            topic_type_ids=[record.topic_type_id],
            forum_folder_ids=[record.forum_folder],
            radius=1234,
        )

        users_list_composer = UsersListComposer(connection)
        res = users_list_composer.get_users_list_for_line_in_change_log(record)
        assert len(res) == 1
        first_user = res[0]
        assert first_user.user_id == user.user_id
        assert first_user.radius == 1234

    def test_coordinates(self, connection: Connection):
        record = LineInChangeLogFactory.build(change_type=ChangeType.topic_first_post_change)

        user = create_user_with_preferences(
            pref_ids=[record.change_type],
            region_ids=[1],
            topic_type_ids=[record.topic_type_id],
            forum_folder_ids=[record.forum_folder],
            user_coordinates=('1.2345', '2.3456'),
            radius=1234,
        )

        users_list_composer = UsersListComposer(connection)
        res = users_list_composer.get_users_list_for_line_in_change_log(record)
        assert len(res) == 1
        first_user = res[0]
        assert first_user.user_id == user.user_id
        assert first_user.user_latitude == '1.2345'
        assert first_user.user_longitude == '2.3456'

    def test_one_age_prefs(self, connection: Connection):
        record = LineInChangeLogFactory.build(change_type=ChangeType.topic_first_post_change)

        user = create_user_with_preferences(
            pref_ids=[record.change_type],
            region_ids=[1],
            topic_type_ids=[record.topic_type_id],
            forum_folder_ids=[record.forum_folder],
            age_periods=[(0, 5), (10, 15)],
        )

        users_list_composer = UsersListComposer(connection)
        res = users_list_composer.get_users_list_for_line_in_change_log(record)
        assert len(res) == 1
        first_user = res[0]
        assert first_user.user_id == user.user_id
        assert first_user.age_periods == [[0, 5], [10, 15]]


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

    def test_filter_users_with_prepared_messages_2(self, connection, dict_notif_type_status_change):
        line_in_change_log = LineInChangeLogFactory.build()
        user = UserFactory.build()
        user_model = db_factories.UserFactory.create_sync(user_id=user.user_id)
        mailing = db_factories.NotifMailingFactory.create_sync(dict_notif_type=dict_notif_type_status_change)
        db_factories.NotifByUserFactory.create_sync(
            user_id=user.user_id, change_log_id=line_in_change_log.change_log_id, mailing=mailing
        )

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_with_prepared_messages()

        assert user not in cropped_users

    def test_filter_users_not_following_this_search_1(self, connection, dict_notif_type_status_change):
        line_in_change_log = LineInChangeLogFactory.build()
        user = UserFactory.build()
        db_factories.UserFactory.create_sync(user_id=user.user_id)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer._filter_users_not_following_this_search()

        assert user in cropped_users

    def test_filter_users_not_following_this_search_2(self, connection, dict_notif_type_status_change):
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

    def test_filter_users_not_following_this_search_3(self, connection, dict_notif_type_status_change):
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

    def test_filter_users_not_following_this_search_4(self, connection, dict_notif_type_status_change):
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

    def test_filter_users_not_following_this_search_5(self, connection, dict_notif_type_status_change):
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

    def test_filter_apply_1(self, connection, dict_notif_type_status_change):
        # complex filter
        line_in_change_log = LineInChangeLogFactory.build(
            city_locations='', search_latitude='54.1234', search_longitude='55.1234'
        )
        user = UserFactory.build(user_latitude='', user_longitude='', radius=0, age_periods=[])
        user_model = db_factories.UserFactory.create_sync(user_id=user.user_id)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer.apply()

        assert user in cropped_users

    def test_filter_apply_2(self, connection, dict_notif_type_status_change):
        # complex filter
        line_in_change_log = LineInChangeLogFactory.build(
            city_locations='', search_latitude='60.1234', search_longitude='60.1234'
        )
        user = UserFactory.build(user_latitude='54.0000', user_longitude='55.0000', radius=1, age_periods=[])
        user_model = db_factories.UserFactory.create_sync(user_id=user.user_id)

        filterer = UserListFilter(connection, line_in_change_log, [user])
        cropped_users = filterer.apply()

        assert user not in cropped_users
