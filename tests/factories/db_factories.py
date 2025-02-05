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
    """
    change_type - 0 - changed_field - "new_search"
    """


class UserFactory(BaseFactory[db_models.User]):
    status = None
    role = 'new_member'


class UserPreferenceFactory(BaseFactory[db_models.UserPreference]):
    preference = 'new_searches'  # status_changes, bot_news, new_searches
    pref_id = 0  # 0, 1,20
    """
    user_pref_type_id - topic_type_id 0,3,4,5
    user_pref_search_whitelist, user_pref_search_filtering - ?? (no permissions)
    user_pref_region - region_id 1
    user_pref_radius - type None,  radius - kilometers

user_pref_age
id  |user_id   |period_name|period_set_date        |period_min|period_max|
----+----------+-----------+-----------------------+----------+----------+
3611| 654123815|0-6        |2023-12-04 07:25:35.106|         0|         6|
3612| 654123815|7-13       |2023-12-04 07:25:35.109|         7|        13|
5506|1094872721|0-6        |2024-05-23 14:43:29.979|         0|         6|
  38| 438843471|0-6        |2023-02-05 09:14:02.928|         0|         6|
  39| 438843471|7-13       |2023-02-05 09:14:02.931|         7|        13|
  41| 438843471|21-50      |2023-02-05 09:14:02.938|        21|        50|    

    """
    pass


class UserRegionalPreferenceFactory(BaseFactory[db_models.UserRegionalPreference]):
    """
    forum_folder_num - short int
    """

    pass


class UserPrefTopicTypeFactory(BaseFactory[db_models.UserPrefTopicType]):
    pass
