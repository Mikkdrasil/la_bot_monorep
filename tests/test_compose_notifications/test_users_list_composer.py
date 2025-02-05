import pytest
from sqlalchemy.engine import Connection

from compose_notifications._utils.notif_common import ChangeType, TopicType
from compose_notifications._utils.users_list_composer import UsersListComposer
from tests.factories import db_factories, db_models
from tests.test_compose_notifications.test_change_log import LineInChageFactory


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

    # TODO user_latitude and user_longitude
    return user


def test_all_change_types(connection: Connection):
    record = LineInChageFactory.build(change_type=ChangeType.topic_first_post_change)

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


def test_one_change_type(connection: Connection):
    record = LineInChageFactory.build(change_type=ChangeType.topic_first_post_change)

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


def test_another_change_type(connection: Connection):
    record = LineInChageFactory.build(change_type=ChangeType.topic_first_post_change)

    user = create_user_with_preferences(
        pref_ids=[ChangeType.bot_news],
        region_ids=[1],
        topic_type_ids=[record.topic_type_id],
        forum_folder_ids=[record.forum_folder],
    )

    users_list_composer = UsersListComposer(connection)
    res = users_list_composer.get_users_list_for_line_in_change_log(record)
    assert not res


def test_radius(connection: Connection):
    record = LineInChageFactory.build(change_type=ChangeType.topic_first_post_change)

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


def test_coordinates(connection: Connection):
    record = LineInChageFactory.build(change_type=ChangeType.topic_first_post_change)

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


def test_one_age_prefs(connection: Connection):
    record = LineInChageFactory.build(change_type=ChangeType.topic_first_post_change)

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
