from functools import lru_cache

import sqlalchemy
import sqlalchemy.ext
import sqlalchemy.orm
import sqlalchemy.pool
from faker import Faker
from polyfactory import Use
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory, T

from _dependencies.commons import sqlalchemy_get_pool
from tests.factories import db_models

faker = Faker('ru_RU')


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
    __allow_none_optionals__ = False


class NotifByUserFactory(BaseFactory[db_models.NotifByUser]):
    message_params = '{"foo":1}'
    message_type = 'text'


class ChangeLogFactory(BaseFactory[db_models.ChangeLog]):
    pass


class SearchFactory(BaseFactory[db_models.Search]):
    pass


class UserFactory(BaseFactory[db_models.User]):
    status = None
    role = 'new_member'


class UserPreferenceFactory(BaseFactory[db_models.UserPreference]):
    pass


class UserPrefAgeFactory(BaseFactory[db_models.UserPrefAge]):
    pass


class UserRegionalPreferenceFactory(BaseFactory[db_models.UserRegionalPreference]):
    pass


class UserCoordinateFactory(BaseFactory[db_models.UserCoordinate]):
    pass


class UserPrefRegionFactory(BaseFactory[db_models.UserPrefRegion]):
    pass


class UserPrefRadiusFactory(BaseFactory[db_models.UserPrefRadiu]):
    pass


class UserPrefTopicTypeFactory(BaseFactory[db_models.UserPrefTopicType]):
    pass


class SearchAttributeFactory(BaseFactory[db_models.SearchAttribute]):
    pass


class SearchActivityFactory(BaseFactory[db_models.SearchActivity]):
    activity_status = 'ongoing'


class DictSearchActivityFactory(BaseFactory[db_models.DictSearchActivity]):
    pass


class CommentFactory(BaseFactory[db_models.Comment]):
    pass
