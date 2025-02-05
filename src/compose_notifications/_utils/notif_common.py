import datetime
import logging
import math
import re
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any

WINDOW_FOR_NOTIFICATIONS_DAYS = 60
COORD_FORMAT = '{0:.5f}'
COORD_PATTERN = r'0?[3-8]\d\.\d{1,10}[\s\w,]{0,10}[01]?[2-9]\d\.\d{1,10}'


class TopicType(IntEnum):
    """
    SQL table 'dict_topic_types'
    """

    search_regular = 0
    search_reverse = 1
    search_patrol = 2
    search_training = 3
    search_info_support = 4
    search_resonance = 5
    event = 10
    info = 20
    all = 30
    unrecognized = 99


SEARCH_TOPIC_TYPES = {0, 1, 2, 3, 4, 5}


class ChangeType(IntEnum):
    """
    SQL table 'dict_notif_types'
    """

    topic_new = 0
    topic_status_change = 1
    topic_title_change = 2
    topic_comment_new = 3
    topic_inforg_comment_new = 4
    topic_field_trip_new = 5
    topic_field_trip_change = 6
    topic_coords_change = 7
    topic_first_post_change = 8
    bot_news = 20
    not_defined = 99
    all = 30


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
    activities: str = ''
    managers: Any = None
    hint_on_coords: Any = None
    hint_on_something: Any = None  # FIXME


@dataclass
class Comment:
    url: str = ''
    text: str = ''
    author_nickname: str = ''
    author_link: str = ''
    search_forum_num: int = 0
    num: int = 0
    # forum_global_id: Any = None  # not needed
    # ignore: Any = None  # not needed


@dataclass
class LineInChangeLog:
    forum_search_num: int
    changed_field: Any
    new_value: Any
    change_log_id: int
    change_type: int  # enum NotifType
    topic_type_id: int = 0  # enum TopicType
    name: str = ''
    link: str = ''
    status: Any = None
    new_status: Any = None
    n_of_replies: int = 0  # not used
    title: str = ''
    age: int = 0
    age_wording: str = ''
    forum_folder: int = 0
    activities: list[str] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    comments_inforg: list[Comment] = field(default_factory=list)
    message: Any = None
    message_object: Any | Message | MessageNewTopic = None  # FIXME - maybe should replace "message"
    processed: bool = False
    managers: list[str] = field(default_factory=list)
    start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    ignore: bool = False
    region: str | None = None
    search_latitude: str | None = None
    search_longitude: str | None = None
    # coords_change_type: Any = None
    city_locations: Any = None
    display_name: str = ''
    age_min: int | None = None
    age_max: int | None = None
    clickable_name: str = ''
    topic_emoji: str = ''


@dataclass
class User:
    user_id: int = 0
    username_telegram: str | None = None
    # notification_preferences: str = None
    # notif_pref_ids_list: list = None
    all_notifs: bool = False
    # topic_type_pref_ids_list: list = None
    user_latitude: str = ''
    user_longitude: str = ''
    # user_regions: list = None  # TODO remove
    user_in_multi_folders: bool = False
    # user_corr_regions: list = None
    user_new_search_notifs: int = 0
    user_role: str = ''  # not used
    age_periods: list = field(default_factory=list)
    radius: int = 0


def add_tel_link(incoming_text: str) -> str:
    """check is text contains phone number and replaces it with clickable version, also removes [tel] tags"""

    # Modifier for all users

    outcome_text = incoming_text
    nums = re.findall(r'(?:\+7|7|8)\s?[\s\-(]?\s?\d{3}[\s\-)]?\s?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', incoming_text)
    for num in nums:
        outcome_text = outcome_text.replace(num, '<code>' + str(num) + '</code>')

    phpbb_tags_to_delete = {'[tel]', '[/tel]'}
    for tag in phpbb_tags_to_delete:
        outcome_text = outcome_text.replace(tag, '', 5)

    return outcome_text


def calc_direction(lat_1: float, lon_1: float, lat_2: float, lon_2: float) -> str:
    points = [
        '&#8593;&#xFE0E;',
        '&#x2197;&#xFE0F;',
        '&#8594;&#xFE0E;',
        '&#8600;&#xFE0E;',
        '&#8595;&#xFE0E;',
        '&#8601;&#xFE0E;',
        '&#8592;&#xFE0E;',
        '&#8598;&#xFE0E;',
    ]
    bearing = calc_bearing(lat_1, lon_1, lat_2, lon_2)
    bearing += 22.5
    bearing = bearing % 360
    bearing = int(bearing / 45)  # values 0 to 7
    nsew = points[bearing]

    return nsew


def calc_bearing(lat_2: float, lon_2: float, lat_1: float, lon_1: float) -> float:
    d_lon_ = lon_2 - lon_1
    x = math.cos(math.radians(lat_2)) * math.sin(math.radians(d_lon_))
    y = math.cos(math.radians(lat_1)) * math.sin(math.radians(lat_2)) - math.sin(math.radians(lat_1)) * math.cos(
        math.radians(lat_2)
    ) * math.cos(math.radians(d_lon_))
    bearing = math.atan2(x, y)  # used to determine the quadrant
    bearing = math.degrees(bearing)

    return bearing


def define_dist_and_dir_to_search(search_lat: str, search_lon: str, user_let: str, user_lon: str) -> tuple[float, str]:
    """define direction & distance from user's home coordinates to search coordinates"""

    earth_radius = 6373.0  # radius of the Earth

    # coordinates in radians
    lat1 = math.radians(float(search_lat))
    lon1 = math.radians(float(search_lon))
    lat2 = math.radians(float(user_let))
    lon2 = math.radians(float(user_lon))

    # change in coordinates
    d_lon = lon2 - lon1

    d_lat = lat2 - lat1

    # Haversine formula
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = earth_radius * c
    dist = round(distance, 1)

    # define direction
    direction = calc_direction(lat1, lon1, lat2, lon2)

    return dist, direction


def get_coords_from_list(input_list) -> tuple[str | None, str | None]:
    """get the list of coords [lat, lon] for the input list of strings"""

    if not input_list:
        return None, None

    coords_in_text = []

    for line in input_list:
        coords_in_text += re.findall(COORD_PATTERN, line)

    if not (coords_in_text and len(coords_in_text) == 1):
        return None, None

    coords_as_text = coords_in_text[0]
    coords_as_list = re.split(r'(?<=\d)[\s,]+(?=\d)', coords_as_text)

    if len(coords_as_list) != 2:
        return None, None

    try:
        got_lat = COORD_FORMAT.format(float(coords_as_list[0]))
        got_lon = COORD_FORMAT.format(float(coords_as_list[1]))
        return got_lat, got_lon

    except Exception as e:  # noqa
        logging.exception(e)
        return None, None
