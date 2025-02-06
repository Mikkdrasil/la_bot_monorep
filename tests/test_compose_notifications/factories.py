from datetime import datetime

from polyfactory.factories import DataclassFactory

from compose_notifications._utils.commons import LineInChangeLog, TopicType, User


class LineInChangeLogFactory(DataclassFactory[LineInChangeLog]):
    topic_type_id = TopicType.search_regular
    forum_search_num = 1
    start_time = datetime.now()
    activities = [1, 2]
    managers = '["manager1","manager2"]'
    clickable_name = 'foo'


class UserFactory(DataclassFactory[User]):
    user_latitude = '60.0000'
    user_longitude = '60.0000'
