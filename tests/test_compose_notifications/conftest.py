from unittest.mock import patch

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from _dependencies.commons import sqlalchemy_get_pool
from compose_notifications._utils.notif_common import ChangeType, TopicType
from tests.factories import db_factories, db_models


@pytest.fixture(autouse=True)
def local_patches():
    with (
        patch('compose_notifications.main.publish_to_pubsub'),
        patch('compose_notifications._utils.notifications_maker.publish_to_pubsub'),
    ):
        yield


@pytest.fixture
def connection() -> Connection:
    pool = sqlalchemy_get_pool(10, 10)
    with pool.connect() as conn:
        yield conn


@pytest.fixture(scope='session')
def default_dict_notif_type() -> db_models.DictNotifType:
    # TODO generate all types
    with db_factories.get_session() as session:
        return get_or_create(
            session,
            db_models.DictNotifType,
            type_id=ChangeType.topic_status_change,
            type_name='new_search',
        )


def get_or_create(session: Session, model, **kwargs):
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance
    else:
        instance = model(**kwargs)
        session.add(instance)
        session.commit()
        return instance
