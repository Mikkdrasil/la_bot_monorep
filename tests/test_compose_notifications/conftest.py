from unittest.mock import patch

import pytest
from sqlalchemy.engine import Connection

from _dependencies.commons import sqlalchemy_get_pool
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
def default_dict_notif_type() -> db_models.DictNotifType:
    with db_factories.get_session() as session:
        if session.query(db_models.DictNotifType).filter(db_models.DictNotifType.type_id == 1).count() == 0:
            session.add(db_models.DictNotifType(type_id=1, type_name='new_search'))
        session.commit()
