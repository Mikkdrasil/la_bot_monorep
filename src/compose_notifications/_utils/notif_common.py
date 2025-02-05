import datetime
from dataclasses import dataclass, field
from typing import Any

WINDOW_FOR_NOTIFICATIONS_DAYS = 60
COORD_FORMAT = '{0:.5f}'
COORD_PATTERN = r'0?[3-8]\d\.\d{1,10}[\s\w,]{0,10}[01]?[2-9]\d\.\d{1,10}'


@dataclass
class Message:
    name: str = ''
    age: str | int = ''
    display_name: str = ''
    clickable_name: str = ''


@dataclass
class MessageNewTopic(Message):
    city_coords: Any = None
    hq_coords: Any = None
    activities: Any = None
    managers: Any = None
    hint_on_coords: Any = None
    hint_on_something: Any = None  # FIXME


@dataclass
class Comment:
    url: str = None
    text: str = None
    author_nickname: str = None
    author_link: str = None
    search_forum_num: Any = None
    num: Any = None
    forum_global_id: Any = None
    ignore: Any = None


@dataclass
class LineInChangeLog:
    forum_search_num: int = None
    topic_type_id: int = None
    change_type: int = None  # it is int from 0 to 99 which represents "change_type" column in change_log
    changed_field: Any = None
    change_id: Any = None  # means change_log_id
    new_value: Any = None
    name: Any = None
    link: Any = None
    status: Any = None
    new_status: Any = None
    n_of_replies: Any = None
    title: Any = None
    age: Any = None
    age_wording: Any = None
    forum_folder: int = None
    activities: list[int] = field(default_factory=list)
    comments: Any = None
    comments_inforg: Any = None
    message: Any = None
    message_object: Any | Message | MessageNewTopic = None  # FIXME
    processed: Any = None
    managers: list[str] = field(default_factory=list)
    start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    ignore: str = None  # "y"
    region: Any = None
    search_latitude: Any = None
    search_longitude: Any = None
    coords_change_type: Any = None
    city_locations: Any = None
    display_name: Any = None
    age_min: Any = None
    age_max: Any = None
    clickable_name: str = ''
    topic_emoji: Any = None


@dataclass
class User:
    user_id: int = None
    username_telegram: str = None
    notification_preferences: str = None
    notif_pref_ids_list: list = None
    all_notifs: list = None
    topic_type_pref_ids_list: list = None
    user_latitude: float = None
    user_longitude: float = None
    user_regions: list = None  # TODO remove
    user_in_multi_folders: bool = True
    user_corr_regions: list = None
    user_new_search_notifs: bool = None
    user_role: str = None
    age_periods: list = None
    radius: float = None
