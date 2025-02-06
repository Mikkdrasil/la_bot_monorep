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
    __set_primary_key__ = False  # primary keys generated automatically by postgres


class DictSearchActivityFactory(BaseFactory[db_models.DictSearchActivity]):
    pass


class DictNotifTypeFactory(BaseFactory[db_models.DictNotifType]):
    __set_primary_key__ = True  # primary keys generated automatically by postgres
    # type_id = Use(BaseFactory.__random__.choice, [1, 2, 3, 4])


class NotifMailingFactory(BaseFactory[db_models.NotifMailing]):
    dict_notif_type = Use(DictNotifTypeFactory.create_sync)


class NotifByUserFactory(BaseFactory[db_models.NotifByUser]):
    message_params = '{"foo":1}'
    message_type = 'text'
    mailing = Use(NotifMailingFactory.create_sync)


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


class CommentFactory(BaseFactory[db_models.Comment]):
    pass


class UserPrefSearchWhitelistFactory(BaseFactory[db_models.UserPrefSearchWhitelist]):
    pass


class UserPrefSearchFiltering(db_models.Base):
    # we have no model for user_pref_search_filtering, only Table. let's make it here
    __table__ = db_models.t_user_pref_search_filtering
    __mapper_args__ = {'primary_key': [db_models.t_user_pref_search_filtering.c.filter_id]}


class UserPrefSearchFilteringFactory(BaseFactory[UserPrefSearchFiltering]):
    pass
