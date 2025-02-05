from unittest.mock import patch

import pytest
from sqlalchemy.engine import Connection

from _dependencies.commons import sqlalchemy_get_pool
from compose_notifications._utils.notif_common import ChangeType, TopicType
from tests.factories import db_factories, db_models


@pytest.fixture(autouse=True)
def local_patches():
    with (
        patch('compose_notifications.main.publish_to_pubsub'),
    ):
        yield


@pytest.fixture
def connection() -> Connection:
    pool = sqlalchemy_get_pool(10, 10)
    with pool.connect() as conn:
        yield conn


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
