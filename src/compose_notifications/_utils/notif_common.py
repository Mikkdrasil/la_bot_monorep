from dataclasses import dataclass


class LineInChangeLog:
    def __init__(
        self,
        forum_search_num=None,
        topic_type_id=None,
        change_type=None,  # it is int from 0 to 99 which represents "change_type" column in change_log
        changed_field=None,
        change_id=None,  # means change_log_id
        new_value=None,
        name=None,
        link=None,
        status=None,
        new_status=None,
        n_of_replies=None,
        title=None,
        age=None,
        age_wording=None,
        forum_folder=None,
        activities=None,
        comments=None,
        comments_inforg=None,
        message=None,
        message_object=None,  # FIXME
        processed=None,
        managers=None,
        start_time=None,
        ignore=None,
        region=None,
        search_latitude=None,
        search_longitude=None,
        coords_change_type=None,
        city_locations=None,
        display_name=None,
        age_min=None,
        age_max=None,
        clickable_name=None,
        topic_emoji=None,
    ):
        self.forum_search_num = forum_search_num
        self.topic_type_id = topic_type_id
        self.change_type = change_type
        self.changed_field = changed_field
        self.change_id = change_id
        self.new_value = new_value
        self.name = name
        self.link = link
        self.status = status
        self.new_status = new_status
        self.n_of_replies = n_of_replies
        self.title = title
        self.age = age
        self.age_wording = age_wording
        self.forum_folder = forum_folder
        self.activities = activities
        self.comments = comments
        self.comments_inforg = comments_inforg
        self.message = message
        self.message_object = message_object
        self.processed = processed
        self.managers = managers
        self.start_time = start_time
        self.ignore = ignore
        self.region = region
        self.search_latitude = search_latitude
        self.search_longitude = search_longitude
        self.coords_change_type = coords_change_type
        self.city_locations = city_locations
        self.display_name = display_name
        self.age_min = age_min
        self.age_max = age_max
        self.clickable_name = clickable_name
        self.topic_emoji = topic_emoji

    def __str__(self):
        return str(
            [
                self.forum_search_num,
                self.change_type,
                self.changed_field,
                self.new_value,
                self.change_id,
                self.name,
                self.link,
                self.status,
                self.n_of_replies,
                self.title,
                self.age,
                self.age_wording,
                self.forum_folder,
                self.search_latitude,
                self.search_longitude,
                self.activities,
                self.comments,
                self.comments_inforg,
                self.message,
                self.processed,
                self.managers,
                self.start_time,
                self.ignore,
                self.region,
                self.coords_change_type,
                self.display_name,
                self.age_min,
                self.age_max,
                self.topic_type_id,
                self.clickable_name,
                self.topic_emoji,
            ]
        )


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
    user_regions: list = None
    user_in_multi_folders: bool = True
    user_corr_regions: list = None
    user_new_search_notifs: bool = None
    user_role: str = None
    age_periods: list = None
    radius: float = None


class Message:
    def __init__(self, name=None, age=None, display_name=None, clickable_name=None):
        self.name = name
        self.age = age
        self.display_name = display_name
        self.clickable_name = clickable_name


class MessageNewTopic(Message):
    def __init__(
        self,
        city_coords=None,
        hq_coords=None,
        activities=None,
        managers=None,
        hint_on_coords=None,
        hint_on_something=None,  # FIXME
    ):
        super().__init__()
        self.city_coords = city_coords
        self.hq_coords = hq_coords
        self.activities = activities
        self.managers = managers
        self.hint_on_coords = hint_on_coords
        self.hint_on_something = hint_on_something  # FIXME


class Comment:
    def __init__(
        self,
        url=None,
        text=None,
        author_nickname=None,
        author_link=None,
        topic_id=None,
        num=None,
        forum_global_id=None,
        ignore=None,
    ):
        self.url = url
        self.text = text
        self.author_nickname = author_nickname
        self.author_link = author_link
        self.search_forum_num = topic_id  # rename topic_id
        self.num = num
        self.forum_global_id = forum_global_id
        self.ignore = ignore

    def __str__(self):
        return str(
            [
                self.url,
                self.text,
                self.author_nickname,
                self.author_link,
                self.search_forum_num,
                self.num,
                self.forum_global_id,
                self.ignore,
            ]
        )


WINDOW_FOR_NOTIFICATIONS_DAYS = 60
coord_format = '{0:.5f}'
coord_pattern = r'0?[3-8]\d\.\d{1,10}[\s\w,]{0,10}[01]?[2-9]\d\.\d{1,10}'
