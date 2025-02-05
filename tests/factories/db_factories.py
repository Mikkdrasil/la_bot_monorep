from functools import lru_cache

import sqlalchemy
import sqlalchemy.ext
import sqlalchemy.orm
import sqlalchemy.pool
from polyfactory import Use
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory, T

from _dependencies.commons import sqlalchemy_get_pool
from tests.factories import db_models


@lru_cache
def get_sessionmaner() -> sqlalchemy.orm.sessionmaker:
    engine = sqlalchemy_get_pool(10, 10)
    return sqlalchemy.orm.sessionmaker(engine, expire_on_commit=False)


def get_session():
    session_maker = get_sessionmaner()
    return session_maker()


class BaseFactory(SQLAlchemyFactory[T]):
    __is_base_factory__ = True
    __set_relationships__ = True
    __session__ = get_session


class NotifByUserFactory(BaseFactory[db_models.NotifByUser]):
    message_params = '{"foo":1}'
    change_log_id = Use(BaseFactory.__random__.randint, 1, 100000000)
    message_type = 'text'


class ChangeLogFactory(BaseFactory[db_models.ChangeLog]):
    pass


class UserFactory(BaseFactory[db_models.User]):
    status = None
    # message_params = '{"foo":1}'
    # change_log_id = Use(BaseFactory.__random__.randint, 1, 100000000)
    # message_type = 'text'


class UserPreferenceFactory(BaseFactory[db_models.UserPreference]):
    pass


class UserRegionalPreferenceFactory(BaseFactory[db_models.UserRegionalPreference]):
    pass


class UserPrefTopicTypeFactory(BaseFactory[db_models.UserPrefTopicType]):
    pass
