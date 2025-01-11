"""compose and save all the text / location messages, then initiate sending via pub-sub"""

import ast
import base64
import datetime
import json
import logging
import math
import random
import re
import urllib.request

import google.cloud.logging
import sqlalchemy
from google.cloud import pubsub_v1, secretmanager

url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
req = urllib.request.Request(url)
req.add_header('Metadata-Flavor', 'Google')
project_id = urllib.request.urlopen(req).read().decode()

client = secretmanager.SecretManagerServiceClient()
publisher = pubsub_v1.PublisherClient()

log_client = google.cloud.logging.Client()
log_client.setup_logging()

WINDOW_FOR_NOTIFICATIONS_DAYS = 60

coord_format = '{0:.5f}'
stat_list_of_recipients = []  # list of users who received notification on new search
fib_list = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]
coord_pattern = r'0?[3-8]\d\.\d{1,10}[\s\w,]{0,10}[01]?[2-9]\d\.\d{1,10}'


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
        self.search_forum_num = topic_id
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


class User:
    def __init__(
        self,
        user_id=None,
        username_telegram=None,  # TODO: to check if it's needed
        notification_preferences=None,  # TODO: to check if it's needed
        notif_pref_ids_list=None,  # TODO: to check if it's needed,
        all_notifs=None,
        topic_type_pref_ids_list=None,  # TODO: to check if it's needed
        user_latitude=None,
        user_longitude=None,
        user_regions=None,  # TODO: COULD BE NEEDED for MULTY-REGION to check if it's needed
        user_in_multi_folders=True,
        user_corr_regions=None,  # FIXME - seems it's not needed anymore
        user_new_search_notifs=None,  # TODO: to check if it's needed
        user_role=None,  # TODO: to check if it's needed
        user_age_periods=None,  # noqa
        radius=None,
    ):
        user_age_periods = []
        self.user_id = user_id
        self.username_telegram = username_telegram
        self.notification_preferences = notification_preferences
        self.notif_pref_ids_list = notif_pref_ids_list
        self.all_notifs = all_notifs
        self.topic_type_pref_ids_list = topic_type_pref_ids_list
        self.user_latitude = user_latitude
        self.user_longitude = user_longitude
        self.user_regions = user_regions
        self.user_in_multi_folders = user_in_multi_folders
        self.user_corr_regions = user_corr_regions
        self.user_new_search_notifs = user_new_search_notifs
        self.role = user_role
        self.age_periods = user_age_periods
        self.radius = radius

    def __str__(self):
        return str(
            [
                self.user_id,
                self.username_telegram,
                self.notification_preferences,
                self.notif_pref_ids_list,
                self.all_notifs,
                self.topic_type_pref_ids_list,
                self.user_latitude,
                self.user_longitude,
                self.user_regions,
                self.user_in_multi_folders,
                self.user_corr_regions,
                self.user_new_search_notifs,
                self.role,
                self.age_periods,
                self.radius,
            ]
        )

    def __eq__(self, other):
        return (
            self.user_id == other.user_id
            and self.username_telegram == other.username_telegram
            and self.notification_preferences == other.notification_preferences
            and self.notif_pref_ids_list == other.notif_pref_ids_list
            and self.topic_type_pref_ids_list == other.topic_type_pref_ids_list
            and self.user_latitude == other.user_latitude
            and self.user_longitude == other.user_longitude
            and self.user_regions == other.user_regions
            and self.user_in_multi_folders == other.user_in_multi_folders
            and self.all_notifs == other.all_notifs
            and self.user_corr_regions == other.user_corr_regions
            and self.user_new_search_notifs == other.user_new_search_notifs
            and self.role == other.role
            and self.age_periods == other.age_periods
            and self.radius == other.radius
        )


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


def sql_connect():
    """connect to google cloud sql"""

    db_user = get_secrets('cloud-postgres-username')
    db_pass = get_secrets('cloud-postgres-password')
    db_name = get_secrets('cloud-postgres-db-name')
    db_conn = get_secrets('cloud-postgres-connection-name')
    db_config = {
        'pool_size': 5,
        'max_overflow': 0,
        'pool_timeout': 0,  # seconds
        'pool_recycle': 60,  # seconds
    }

    try:
        pool = sqlalchemy.create_engine(
            sqlalchemy.engine.url.URL(
                'postgresql+pg8000',
                username=db_user,
                password=db_pass,
                database=db_name,
                query={'unix_sock': f'/cloudsql/{db_conn}/.s.PGSQL.5432'},
            ),
            **db_config,
        )
        pool.dialect.description_encoding = None
        logging.info('sql connection set')

    except Exception as e:
        logging.error('sql connection was not set: ' + repr(e))
        logging.exception(e)
        pool = None

    return pool


def get_secrets(secret_request):
    """get secret stored in GCP"""

    name = f'projects/{project_id}/secrets/{secret_request}/versions/latest'
    response = client.access_secret_version(name=name)

    return response.payload.data.decode('UTF-8')


def age_writer(age):
    """compose an age string with the right form of years in Russian"""

    if age:
        a = age // 100
        b = (age - a * 100) // 10
        c = age - a * 100 - b * 10
        if c == 1 and b != 1:
            wording = str(age) + ' год'
        elif (c == 2 or c == 3 or c == 4) and b != 1:
            wording = str(age) + ' года'
        else:
            wording = str(age) + ' лет'
    else:
        wording = ''

    return wording


def define_family_name(title_string, predefined_fam_name):
    """define family name if it's not available as A SEPARATE FIELD in Searches table"""

    # if family name is already defined
    if predefined_fam_name:
        fam_name = predefined_fam_name

    # if family name needs to be defined
    else:
        string_by_word = title_string.split()
        # exception case: when Family Name is third word
        # it happens when first two either Найден Жив or Найден Погиб with different word forms
        if string_by_word[0][0:4].lower() == 'найд':
            fam_name = string_by_word[2]

        # case when "Поиск приостановлен"
        elif string_by_word[1][0:8].lower() == 'приостан':
            fam_name = string_by_word[2]

        # case when "Поиск остановлен"
        elif string_by_word[1][0:8].lower() == 'остановл':
            fam_name = string_by_word[2]

        # all the other cases
        else:
            fam_name = string_by_word[1]

    return fam_name


def define_dist_and_dir_to_search(search_lat, search_lon, user_let, user_lon):
    """define direction & distance from user's home coordinates to search coordinates"""

    def calc_bearing(lat_2, lon_2, lat_1, lon_1):
        d_lon_ = lon_2 - lon_1
        x = math.cos(math.radians(lat_2)) * math.sin(math.radians(d_lon_))
        y = math.cos(math.radians(lat_1)) * math.sin(math.radians(lat_2)) - math.sin(math.radians(lat_1)) * math.cos(
            math.radians(lat_2)
        ) * math.cos(math.radians(d_lon_))
        bearing = math.atan2(x, y)  # used to determine the quadrant
        bearing = math.degrees(bearing)

        return bearing

    def calc_direction(lat_1, lon_1, lat_2, lon_2):
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


def process_pubsub_message(event):
    """get the readable message from incoming pub/sub call"""

    # receive message text from pub/sub
    try:
        if 'data' in event:
            received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
            encoded_to_ascii = eval(received_message_from_pubsub)
            data_in_ascii = encoded_to_ascii['data']
            message_in_ascii = data_in_ascii['message']
        else:
            message_in_ascii = 'ERROR: I cannot read message from pub/sub'

    except Exception as e:
        message_in_ascii = 'ERROR: I cannot read message from pub/sub'
        logging.exception(e)

    logging.info(f'received message from pub/sub: {message_in_ascii}')

    return message_in_ascii


def compose_new_records_from_change_log(conn):
    """compose the New Records list of the unique New Records in Change Log: one Record = One line in Change Log"""

    delta_in_cl = conn.execute(
        """SELECT search_forum_num, changed_field, new_value, id, change_type FROM change_log
        WHERE notification_sent is NULL
        OR notification_sent='s' ORDER BY id LIMIT 1; """
    ).fetchall()

    if not delta_in_cl:
        logging.info('no new records found in PSQL')
        return None

    if not len(list(delta_in_cl)) > 0:
        logging.info(f'new record is found in PSQL, however it is not list: {delta_in_cl}')
        return None

    one_line_in_change_log = [i for i in delta_in_cl[0]]

    if not one_line_in_change_log:
        logging.info(f'new record is found in PSQL, however it is not list: {delta_in_cl}, {one_line_in_change_log}')
        return None

    logging.info(f'new record is {one_line_in_change_log}')
    new_record = LineInChangeLog()
    new_record.forum_search_num = one_line_in_change_log[0]
    new_record.changed_field = one_line_in_change_log[1]
    new_record.new_value = one_line_in_change_log[2]
    new_record.change_id = one_line_in_change_log[3]
    new_record.change_type = one_line_in_change_log[4]

    # TODO – there was a filtering for duplication: Inforg comments vs All Comments, but after restructuring
    #  of the scrip tech solution stopped working. The new filtering solution to be developed

    logging.info(f'New Record composed from Change Log: {str(new_record)}')

    return new_record


def enrich_new_record_from_searches(conn, r_line):
    """add the additional data from Searches into New Records"""

    try:
        sql_text = sqlalchemy.text(
            """WITH
            s AS (
                SELECT search_forum_num, forum_search_title, num_of_replies, family_name, age,
                    forum_folder_id, search_start_time, display_name, age_min, age_max, status, city_locations,
                    topic_type_id
                FROM searches
                WHERE search_forum_num = :a
            ),
            ns AS (
                SELECT s.search_forum_num, s.status, s.forum_search_title, s.num_of_replies, s.family_name,
                    s.age, s.forum_folder_id, sa.latitude, sa.longitude, s.search_start_time, s.display_name,
                    s.age_min, s.age_max, s.status, s.city_locations, s.topic_type_id
                FROM s
                LEFT JOIN search_coordinates as sa
                ON s.search_forum_num=sa.search_id
            )
            SELECT ns.*, f.folder_display_name
            FROM ns
            LEFT JOIN geo_folders_view AS f
            ON ns.forum_folder_id = f.folder_id;"""
        )

        s_line = conn.execute(sql_text, a=r_line.forum_search_num).fetchone()

        if not s_line:
            logging.info('New Record WERE NOT enriched from Searches as there was no record in searches')
            logging.info(f'New Record is {r_line}')
            logging.info(f'extract from searches is {s_line}')
            logging.exception('no search in searches table!')
            return r_line

        r_line.status = s_line[1]
        r_line.link = f'https://lizaalert.org/forum/viewtopic.php?t={r_line.forum_search_num}'
        r_line.title = s_line[2]
        r_line.n_of_replies = s_line[3]
        r_line.name = define_family_name(r_line.title, s_line[4])  # cuz not all the records has names in S
        r_line.age = s_line[5]
        r_line.age_wording = age_writer(s_line[5])
        r_line.forum_folder = s_line[6]
        r_line.search_latitude = s_line[7]
        r_line.search_longitude = s_line[8]
        r_line.start_time = s_line[9]
        r_line.display_name = s_line[10]
        r_line.age_min = s_line[11]
        r_line.age_max = s_line[12]
        r_line.new_status = s_line[13]
        r_line.city_locations = s_line[14]
        r_line.topic_type_id = s_line[15]
        r_line.region = s_line[16]

        logging.info(f'TEMP – FORUM_FOLDER = {r_line.forum_folder}, while s_line = {str(s_line)}')
        logging.info(f'TEMP – CITY LOCS = {r_line.city_locations}')
        logging.info(f'TEMP – STATUS_OLD = {r_line.status}, STATUS_NEW = {r_line.new_status}')
        logging.info(f'TEMP – TOPIC_TYPE = {r_line.topic_type_id}')

        # case: when new search's status is already not "Ищем" – to be ignored
        if r_line.status != 'Ищем' and r_line.change_type in {0, 8}:  # "new_search" & "first_post_change":
            r_line.ignore = 'y'

        # limit notification sending only for searches started 60 days ago
        # 60 days – is a compromise and can be reviewed if community votes for another setting
        try:
            latest_when_alert = r_line.start_time + datetime.timedelta(days=WINDOW_FOR_NOTIFICATIONS_DAYS)
            if latest_when_alert < datetime.datetime.now() and r_line.forum_folder not in {333, 305, 334, 306, 190}:
                r_line.ignore = 'y'

                # DEBUG purposes only
                notify_admin(f'ignoring old search upd {r_line.forum_search_num} with start time {r_line.start_time}')
            # FIXME – 03.12.2023 – checking that Samara is not filtered by 60 days
            if latest_when_alert < datetime.datetime.now() and r_line.forum_folder in {333, 305, 334, 306, 190}:
                notify_admin(f'☀️ SAMARA >60 {r_line.link}')
            # FIXME ^^^

        except:  # noqa
            pass

        logging.info('New Record enriched from Searches')

    except Exception as e:
        logging.error('Not able to enrich New Records from Searches:')
        logging.exception(e)

    return r_line


def enrich_new_record_with_search_activities(conn, r_line):
    """add the lists of current searches' activities to New Record"""

    try:
        list_of_activities = conn.execute("""SELECT sa.search_forum_num, dsa.activity_name from search_activities sa
        LEFT JOIN dict_search_activities dsa ON sa.activity_type=dsa.activity_id
        WHERE
        sa.activity_type <> '9 - hq closed' AND
        sa.activity_type <> '8 - info' AND
        sa.activity_status = 'ongoing' ORDER BY sa.id; """).fetchall()

        # look for matching Forum Search Numbers in New Records List & Search Activities
        temp_list_of_activities = []
        for a_line in list_of_activities:
            # when match is found
            if r_line.forum_search_num == a_line[0]:
                temp_list_of_activities.append(a_line[1])
        r_line.activities = temp_list_of_activities

        logging.info('New Record enriched with Search Activities')

    except Exception as e:
        logging.error('Not able to enrich New Records with Search Activities: ' + str(e))
        logging.exception(e)

    return r_line


def enrich_new_record_with_managers(conn, r_line):
    """add the lists of current searches' managers to the New Record"""

    try:
        list_of_managers = conn.execute("""
        SELECT search_forum_num, attribute_name, attribute_value
        FROM search_attributes
        WHERE attribute_name='managers'
        ORDER BY id; """).fetchall()

        # look for matching Forum Search Numbers in New Records List & Search Managers
        for m_line in list_of_managers:
            # when match is found
            if r_line.forum_search_num == m_line[0] and m_line[2] != '[]':
                r_line.managers = m_line[2]

        logging.info('New Record enriched with Managers')

    except Exception as e:
        logging.error('Not able to enrich New Records with Managers: ' + str(e))
        logging.exception(e)

    return r_line


def enrich_new_record_with_comments(conn, type_of_comments, r_line):
    """add the lists of new comments + new inforg comments to the New Record"""

    try:
        if type_of_comments == 'all':
            comments = conn.execute("""SELECT
                                          comment_url, comment_text, comment_author_nickname, comment_author_link,
                                          search_forum_num, comment_num, comment_global_num
                                       FROM comments WHERE notification_sent IS NULL;""").fetchall()

        elif type_of_comments == 'inforg':
            comments = conn.execute("""SELECT
                                        comment_url, comment_text, comment_author_nickname, comment_author_link,
                                        search_forum_num, comment_num, comment_global_num
                                    FROM comments WHERE notif_sent_inforg IS NULL
                                    AND LOWER(LEFT(comment_author_nickname,6))='инфорг'
                                    AND comment_author_nickname!='Инфорг кинологов';""").fetchall()
        else:
            comments = None

        # look for matching Forum Search Numbers in New Record List & Comments
        if r_line.change_type in {3, 4}:  # {'replies_num_change', 'inforg_replies'}:
            temp_list_of_comments = []
            for c_line in comments:
                # when match of Forum Numbers is found
                if r_line.forum_search_num == c_line[4]:
                    # check for empty comments
                    if c_line[1] and c_line[1][0:6].lower() != 'резерв':
                        comment = Comment()
                        comment.url = c_line[0]
                        comment.text = c_line[1]

                        # limitation for extra long messages
                        if len(comment.text) > 3500:
                            comment.text = comment.text[:2000] + '...'

                        comment.author_link = c_line[3]
                        comment.search_forum_num = c_line[4]
                        comment.num = c_line[5]

                        # some nicknames can be like >>Белый<< which crashes html markup -> we delete symbols
                        comment.author_nickname = c_line[2]
                        if comment.author_nickname.find('>') > -1:
                            comment.author_nickname = comment.author_nickname.replace('>', '')
                        if comment.author_nickname.find('<') > -1:
                            comment.author_nickname = comment.author_nickname.replace('<', '')

                        temp_list_of_comments.append(comment)

            if type_of_comments == 'all':
                r_line.comments = temp_list_of_comments
            elif type_of_comments == 'inforg':
                r_line.comments_inforg = temp_list_of_comments

        logging.info(f'New Record enriched with Comments for {type_of_comments}')

    except Exception as e:
        logging.error(f'Not able to enrich New Records with Comments for {type_of_comments}:')
        logging.exception(e)

    return r_line


def compose_com_msg_on_new_topic(line):
    """compose the common, user-independent message on new topic (search, event)"""

    start = line.start_time
    activities = line.activities
    managers = line.managers
    clickable_name = line.clickable_name
    topic_type_id = line.topic_type_id

    line_ignore = None
    now = datetime.datetime.now()
    days_since_topic_start = (now - start).days

    # FIXME – temp limitation for only topics - cuz we don't want to filter event.
    #  Once events messaging will go smooth, this limitation to be removed.
    #  03.12.2023 – Removed to check
    # if topic_type_id in {0, 1, 2, 3, 4, 5}:
    # FIXME ^^^

    if days_since_topic_start >= 2:  # we do not notify users on "new" topics appeared >=2 days ago:
        return [None, None, None], None, 'y'  # topic to be ignored

    message = MessageNewTopic()

    if topic_type_id == 10:  # new event
        clickable_name = f'🗓️Новое мероприятие!\n{clickable_name}'
        message.clickable_name = clickable_name
        return [clickable_name, None, None], message, line_ignore

    # 1. List of activities – user-independent
    msg_1 = ''
    if activities:
        for line in activities:
            msg_1 += f'{line}\n'
    message.activities = msg_1

    # 2. Person
    msg_2 = clickable_name

    if clickable_name:
        message.clickable_name = clickable_name

    # 3. List of managers – user-independent
    msg_3 = ''
    if managers:
        try:
            managers_list = ast.literal_eval(managers)
            msg_3 += 'Ответственные:'
            for manager in managers_list:
                line = add_tel_link(manager)
                msg_3 += f'\n &#8226; {line}'

        except Exception as e:
            logging.error('Not able to compose New Search Message text with Managers: ' + str(e))
            logging.exception(e)

        message.managers = msg_3

    logging.info('msg 2 + msg 1 + msg 3: ' + str(msg_2) + ' // ' + str(msg_1) + ' // ' + str(msg_3))

    return [msg_2, msg_1, msg_3], message, line_ignore  # 1 - person, 2 - activities, 3 - managers


def compose_com_msg_on_status_change(line):
    """compose the common, user-independent message on search status change"""

    status = line.status
    region = line.region
    clickable_name = line.clickable_name

    if status == 'Ищем':
        status_info = 'Поиск возобновлён'
    elif status == 'Завершен':
        status_info = 'Поиск завершён'
    else:
        status_info = status

    msg_1 = f'{status_info} – изменение статуса по {clickable_name}'

    msg_2 = f' ({region})' if region else None

    return msg_1, msg_2


def compose_com_msg_on_new_comments(line):
    """compose the common, user-independent message on ALL search comments change"""

    url_prefix = 'https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
    activity = 'мероприятию' if line.topic_type_id == 10 else 'поиску'

    msg = ''
    for comment in line.comments:
        if comment.text:
            comment_text = f'{comment.text[:500]}...' if len(comment.text) > 500 else comment.text
            msg += (
                f' &#8226; <a href="{url_prefix}{comment.author_link}">{comment.author_nickname}</a>: '
                f'<i>«<a href="{comment.url}">{comment_text}</a>»</i>\n'
            )

    msg = f'Новые комментарии по {activity} {line.clickable_name}:\n{msg}' if msg else ''

    return msg, None


def compose_com_msg_on_inforg_comments(line):
    """compose the common, user-independent message on INFORG search comments change"""

    # region_to_show = f' ({region})' if region else ''
    url_prefix = 'https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='

    msg_1, msg_2 = None, None
    msg_3 = ''
    if line.comments_inforg:
        author = None
        for comment in line.comments_inforg:
            if comment.text:
                author = f'<a href="{url_prefix}{comment.author_link}">{comment.author_nickname}</a>'
                msg_3 += f'<i>«<a href="{comment.url}">{comment.text}</a>»</i>\n'

        msg_3 = f':\n{msg_3}'

        msg_1 = f'{line.topic_emoji}Сообщение от {author} по {line.clickable_name}'
        if line.region:
            msg_2 = f' ({line.region})'

    return msg_1, msg_2, msg_3


def compose_com_msg_on_title_change(line):
    """compose the common, user-independent message on search title change"""

    activity = 'мероприятия' if line.topic_type_id == 10 else 'поиска'
    msg = f'{line.title} – обновление заголовка {activity} по {line.clickable_name}'

    return msg


def get_coords_from_list(input_list):
    """get the list of coords [lat, lon] for the input list of strings"""

    if not input_list:
        return None, None

    coords_in_text = []

    for line in input_list:
        coords_in_text += re.findall(coord_pattern, line)

    if not (coords_in_text and len(coords_in_text) == 1):
        return None, None

    coords_as_text = coords_in_text[0]
    coords_as_list = re.split(r'(?<=\d)[\s,]+(?=\d)', coords_as_text)

    if len(coords_as_list) != 2:
        return None, None

    try:
        got_lat = coord_format.format(float(coords_as_list[0]))
        got_lon = coord_format.format(float(coords_as_list[1]))
        return got_lat, got_lon

    except Exception as e:  # noqa
        logging.exception(e)
        return None, None


def compose_com_msg_on_first_post_change(record):
    """compose the common, user-independent message on search first post change"""

    message = record.new_value
    clickable_name = record.clickable_name
    old_lat = record.search_latitude
    old_lon = record.search_longitude
    type_id = record.topic_type_id

    region = '{region}'  # to be filled in on a stage of Individual Message preparation
    list_of_additions = None
    list_of_deletions = None

    if message and message[0] == '{':
        message_dict = ast.literal_eval(message) if message else {}

        if 'del' in message_dict.keys() and 'add' in message_dict.keys():
            message = ''
            list_of_deletions = message_dict['del']
            if list_of_deletions:
                message += '➖Удалено:\n<s>'
                for line in list_of_deletions:
                    message += f'{line}\n'
                message += '</s>'

            list_of_additions = message_dict['add']
            if list_of_additions:
                if message:
                    message += '\n'
                message += '➕Добавлено:\n'
                for line in list_of_additions:
                    # majority of coords in RU: lat in [30-80], long in [20-180]
                    updated_line = re.sub(coord_pattern, '<code>\g<0></code>', line)
                    message += f'{updated_line}\n'
        else:
            message = message_dict['message']

    coord_change_phrase = ''
    add_lat, add_lon = get_coords_from_list(list_of_additions)
    del_lat, del_lon = get_coords_from_list(list_of_deletions)

    if old_lat and old_lon:
        old_lat = coord_format.format(float(old_lat))
        old_lon = coord_format.format(float(old_lon))

    if add_lat and add_lon and del_lat and del_lon and (add_lat != del_lat or add_lon != del_lon):
        distance, direction = define_dist_and_dir_to_search(del_lat, del_lon, add_lat, add_lon)
    elif add_lat and add_lon and del_lat and del_lon and (add_lat == del_lat and add_lon == del_lon):
        distance, direction = None, None
    elif add_lat and add_lon and old_lat and old_lon and (add_lat != old_lat or add_lon != old_lon):
        distance, direction = define_dist_and_dir_to_search(old_lat, old_lon, add_lat, add_lon)
    else:
        distance, direction = None, None

    if distance and direction:
        if distance >= 1:
            coord_change_phrase = f'\n\nКоординаты сместились на ~{int(distance)} км {direction}'
        else:
            coord_change_phrase = f'\n\nКоординаты сместились на ~{int(distance * 1000)} метров {direction}'

    if not message:
        return ''

    if type_id in {0, 1, 2, 3, 4, 5}:
        resulting_message = (
            f'{record.topic_emoji}🔀Изменения в первом посте по {clickable_name}{region}:\n\n{message}'
            f'{coord_change_phrase}'
        )
    elif type_id == 10:
        resulting_message = (
            f'{record.topic_emoji}Изменения в описании мероприятия {clickable_name}{region}:\n\n{message}'
        )
    else:
        resulting_message = ''

    return resulting_message


def add_tel_link(incoming_text, modifier='all'):
    """check is text contains phone number and replaces it with clickable version, also removes [tel] tags"""

    outcome_text = None

    # Modifier for all users
    if modifier == 'all':
        outcome_text = incoming_text
        nums = re.findall(r'(?:\+7|7|8)\s?[\s\-(]?\s?\d{3}[\s\-)]?\s?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', incoming_text)
        for num in nums:
            outcome_text = outcome_text.replace(num, '<code>' + str(num) + '</code>')

        phpbb_tags_to_delete = {'[tel]', '[/tel]'}
        for tag in phpbb_tags_to_delete:
            outcome_text = outcome_text.replace(tag, '', 5)

    # Modifier for Admin
    else:
        pass

    return outcome_text


def enrich_new_record_with_clickable_name(line):
    """add clickable name to the record"""

    if line.topic_type_id in {0, 1, 2, 3, 4, 5}:  # if it's search
        if line.display_name:
            line.clickable_name = f'<a href="{line.link}">{line.display_name}</a>'
        else:
            if line.name:
                name = line.name
            else:
                name = 'БВП'
            age_info = f' {line.age_wording}' if (name[0].isupper() and line.age and line.age != 0) else ''
            line.clickable_name = f'<a href="{line.link}">{name}{age_info}</a>'
    else:  # if it's event or something else
        line.clickable_name = f'<a href="{line.link}">{line.title}</a>'

    return line


def enrich_new_record_with_emoji(line):
    """add specific emoji based on topic (search) type"""

    topic_type_id = line.topic_type_id
    topic_type_dict = {
        0: '',  # search regular
        1: '🏠',  # search reverse
        2: '🚓',  # search patrol
        3: '🎓',  # search training
        4: 'ℹ️',  # search info support
        5: '🚨',  # search resonance
        10: '📝',  # event
    }
    if topic_type_id:
        line.topic_emoji = topic_type_dict[topic_type_id]
    else:
        line.topic_emoji = ''

    return line


def enrich_new_record_with_com_message_texts(line):
    """add user-independent message text to the New Records"""

    last_line = None

    try:
        last_line = line

        if line.change_type == 0:  # new topic: new search, new event
            line.message, line.message_object, line.ignore = compose_com_msg_on_new_topic(line)
        elif line.change_type == 1 and line.topic_type_id in {0, 1, 2, 3, 4, 5}:  # status change for search:
            line.message = compose_com_msg_on_status_change(line)
        elif line.change_type == 2:  # 'title_change':
            line.message = compose_com_msg_on_title_change(line)
        elif line.change_type == 3:  # 'replies_num_change':
            line.message = compose_com_msg_on_new_comments(line)
        elif line.change_type == 4:  # 'inforg_replies':
            line.message = compose_com_msg_on_inforg_comments(line)
        elif line.change_type == 8:  # first_post_change
            line.message = compose_com_msg_on_first_post_change(line)

        logging.info('New Record enriched with common Message Text')

    except Exception as e:
        logging.error('Not able to enrich New Record with common Message Texts:' + str(e))
        logging.exception(e)
        logging.info('FOR DEBUG OF ERROR – line is: ' + str(last_line))

    return line


def compose_users_list_from_users(conn, new_record):
    """compose the Users list from the tables Users & User Coordinates: one Record = one user"""

    list_of_users = []

    try:
        analytics_prefix = 'users list'
        analytics_start = datetime.datetime.now()

        sql_text_psy = sqlalchemy.text("""
                WITH
                    user_list AS (
                        SELECT user_id, username_telegram, role
                        FROM users WHERE status IS NULL or status='unblocked'),
                    user_notif_pref_prep AS (
                        SELECT user_id, array_agg(pref_id) aS agg
                        FROM user_preferences GROUP BY user_id),
                    user_notif_type_pref AS (
                        SELECT user_id, CASE WHEN 30 = ANY(agg) THEN True ELSE False END AS all_notifs
                        FROM user_notif_pref_prep
                        WHERE (30 = ANY(agg) OR :a = ANY(agg))
                            AND NOT (4/*topic_inforg_comment_new*/ = ANY(agg)
                                AND :a = 2/*topic_title_change*/)),/*AK20240409:issue13*/
                    user_folders_prep AS (
                        SELECT user_id, forum_folder_num,
                            CASE WHEN count(forum_folder_num) OVER (PARTITION BY user_id) > 1
                                THEN TRUE ELSE FALSE END as multi_folder
                        FROM user_regional_preferences),
                    user_folders AS (
                        SELECT user_id, forum_folder_num, multi_folder
                        FROM user_folders_prep WHERE forum_folder_num= :b),
                    user_topic_pref_prep AS (
                        SELECT user_id, array_agg(topic_type_id) aS agg
                        FROM user_pref_topic_type GROUP BY user_id),
                    user_topic_type_pref AS (
                        SELECT user_id, agg AS all_types
                        FROM user_topic_pref_prep
                        WHERE 30 = ANY(agg) OR :c = ANY(agg)),
                    user_short_list AS (
                        SELECT ul.user_id, ul.username_telegram, ul.role , uf.multi_folder, up.all_notifs
                        FROM user_list as ul
                        LEFT JOIN user_notif_type_pref AS up
                        ON ul.user_id=up.user_id
                        LEFT JOIN user_folders AS uf
                        ON ul.user_id=uf.user_id
                        LEFT JOIN user_topic_type_pref AS ut
                        ON ul.user_id=ut.user_id
                        WHERE
                            uf.forum_folder_num IS NOT NULL AND
                            up.all_notifs IS NOT NULL AND
                            ut.all_types IS NOT NULL),
                    user_with_loc AS (
                        SELECT u.user_id, u.username_telegram, uc.latitude, uc.longitude,
                            u.role, u.multi_folder, u.all_notifs
                        FROM user_short_list AS u
                        LEFT JOIN user_coordinates as uc
                        ON u.user_id=uc.user_id)

                SELECT ns.user_id, ns.username_telegram, ns.latitude, ns.longitude, ns.role,
                    st.num_of_new_search_notifs, ns.multi_folder, ns.all_notifs
                FROM user_with_loc AS ns
                LEFT JOIN user_stat st
                ON ns.user_id=st.user_id
                /*action='get_user_list_filtered_by_folder_and_notif_type' */;""")

        users_short_version = conn.execute(
            sql_text_psy, a=new_record.change_type, b=new_record.forum_folder, c=new_record.topic_type_id
        ).fetchall()

        analytics_sql_finish = datetime.datetime.now()
        duration_sql = round((analytics_sql_finish - analytics_start).total_seconds(), 2)
        logging.info(f'time: {analytics_prefix} sql – {duration_sql} sec')

        if users_short_version:
            logging.info(f'{users_short_version}')
            users_short_version = list(users_short_version)

        for line in users_short_version:
            new_line = User(
                user_id=line[0],
                username_telegram=line[1],
                user_latitude=line[2],
                user_longitude=line[3],
                user_role=line[4],
                user_in_multi_folders=line[6],
                all_notifs=line[7],
            )
            if line[5] == 'None' or line[5] is None:
                new_line.user_new_search_notifs = 0
            else:
                new_line.user_new_search_notifs = int(line[5])

            list_of_users.append(new_line)

        analytics_match_finish = datetime.datetime.now()
        duration_match = round((analytics_match_finish - analytics_sql_finish).total_seconds(), 2)
        logging.info(f'time: {analytics_prefix} match – {duration_match} sec')
        duration_full = round((analytics_match_finish - analytics_start).total_seconds(), 2)
        logging.info(f'time: {analytics_prefix} end-to-end – {duration_full} sec')

        logging.info('User List composed')

    except Exception as e:
        logging.error('Not able to compose Users List: ' + repr(e))
        logging.exception(e)

    return list_of_users


def enrich_users_list_with_age_periods(conn, list_of_users):
    """add the data on Lost people age notification preferences from user_pref_age into users List"""

    try:
        notif_prefs = conn.execute("""SELECT user_id, period_min, period_max FROM user_pref_age;""").fetchall()

        if not notif_prefs:
            return list_of_users

        number_of_enrichments_old = 0
        number_of_enrichments = 0
        for np_line in notif_prefs:
            new_period = [np_line[1], np_line[2]]

            for u_line in list_of_users:
                if u_line.user_id == np_line[0]:
                    u_line.age_periods.append(new_period)
                    number_of_enrichments += 1

        logging.info(f'Users List enriched with Age Prefs, OLD num of enrichments is {number_of_enrichments_old}')
        logging.info(f'Users List enriched with Age Prefs, num of enrichments is {number_of_enrichments}')

    except Exception as e:
        logging.info('Not able to enrich Users List with Age Prefs')
        logging.exception(e)

    return list_of_users


def enrich_users_list_with_radius(conn, list_of_users):
    """add the data on distance notification preferences from user_pref_radius into users List"""

    try:
        notif_prefs = conn.execute("""SELECT user_id, radius FROM user_pref_radius;""").fetchall()

        if not notif_prefs:
            return None

        number_of_enrichments = 0
        for np_line in notif_prefs:
            for u_line in list_of_users:
                if u_line.user_id == np_line[0]:
                    u_line.radius = int(round(np_line[1], 0))
                    number_of_enrichments += 1
                    print(f'TEMP - RADIUS user_id = {u_line.user_id}, radius = {u_line.radius}')

        logging.info(f'Users List enriched with Radius, num of enrichments is {number_of_enrichments}')

    except Exception as e:
        logging.info('Not able to enrich Users List with Radius')
        logging.exception(e)

    return list_of_users


def get_list_of_admins_and_testers(conn):
    """get the list of users with admin & testers roles from PSQL"""

    list_of_admins = []
    list_of_testers = []

    try:
        user_roles = conn.execute("""SELECT user_id, role FROM user_roles;""").fetchall()

        for line in user_roles:
            if line[1] == 'admin':
                list_of_admins.append(line[0])
            elif line[1] == 'tester':
                list_of_testers.append(line[0])

        logging.info('Got the Lists of Admins & Testers')

    except Exception as e:
        logging.info('Not able to get the lists of Admins & Testers ')
        logging.exception(e)

    return list_of_admins, list_of_testers


def record_notification_statistics(conn):
    """records +1 into users' statistics of new searches notification. needed only for usability tips"""

    global stat_list_of_recipients

    dict_of_user_and_number_of_new_notifs = {i: stat_list_of_recipients.count(i) for i in stat_list_of_recipients}

    try:
        for user_id in dict_of_user_and_number_of_new_notifs:
            number_to_add = dict_of_user_and_number_of_new_notifs[user_id]

            sql_text = sqlalchemy.text("""
            INSERT INTO user_stat (user_id, num_of_new_search_notifs)
            VALUES(:a, :b)
            ON CONFLICT (user_id) DO
            UPDATE SET num_of_new_search_notifs = :b +
            (SELECT num_of_new_search_notifs from user_stat WHERE user_id = :a)
            WHERE user_stat.user_id = :a;
            """)
            conn.execute(sql_text, a=int(user_id), b=int(number_to_add))

    except Exception as e:
        logging.error('Recording statistics in notification script failed' + repr(e))
        logging.exception(e)

    return None


def iterate_over_all_users(conn, admins_list, new_record, list_of_users, function_id):
    """initiates a full cycle for all messages composition for all the users"""

    def save_to_sql_notif_by_user(
        mailing_id_,
        user_id_,
        message_,
        message_without_html_,
        message_type_,
        message_params_,
        message_group_id_,
        change_log_id_,
    ):
        """save to sql table notif_by_user the new message"""

        # record into SQL table notif_by_user
        sql_text_ = sqlalchemy.text("""
                            INSERT INTO notif_by_user (
                                mailing_id,
                                user_id,
                                message_content,
                                message_text,
                                message_type,
                                message_params,
                                message_group_id,
                                change_log_id,
                                created)
                            VALUES (:a, :b, :c, :d, :e, :f, :g, :h, :i);
                            """)

        conn.execute(
            sql_text_,
            a=mailing_id_,
            b=user_id_,
            c=message_,
            d=message_without_html_,
            e=message_type_,
            f=message_params_,
            g=message_group_id_,
            h=change_log_id_,
            i=datetime.datetime.now(),
        )

        return None

    def get_from_sql_if_was_notified_already(user_id_, message_type_, change_log_id_):
        """check in sql if this user was already notified re this change_log record
        works for every user during iterations over users"""

        sql_text_ = sqlalchemy.text("""
            SELECT EXISTS (
                SELECT
                    message_id
                FROM
                    notif_by_user
                WHERE
                    completed IS NOT NULL AND
                    user_id=:b AND
                    message_type=:c AND
                    change_log_id=:a
            )
            /*action='get_from_sql_if_was_notified_already_new'*/
            ;
        """)

        user_was_already_notified = conn.execute(sql_text_, a=change_log_id_, b=user_id_, c=message_type_).fetchone()[0]

        return user_was_already_notified

    def get_from_sql_list_of_users_with_prepared_message(change_log_id_):
        """check what is the list of users for whom we already composed messages for the given change_log record"""

        sql_text_ = sqlalchemy.text("""
            SELECT
                user_id
            FROM
                notif_by_user
            WHERE
                created IS NOT NULL AND
                change_log_id=:a

            /*action='get_from_sql_list_of_users_with_already_composed_messages 2.0'*/
            ;
            """)

        raw_data_ = conn.execute(sql_text_, a=change_log_id_).fetchall()
        # TODO: to delete
        logging.info('list of user with composed messages:')
        logging.info(raw_data_)

        users_who_were_composed = []
        for line in raw_data_:
            users_who_were_composed.append(line[0])

        return users_who_were_composed

    def get_the_new_group_id():
        """define the max message_group_id in notif_by_user and add +1"""

        raw_data_ = conn.execute("""SELECT MAX(message_group_id) FROM notif_by_user
        /*action='get_the_new_group_id'*/
        ;""").fetchone()

        if raw_data_[0]:
            next_id = raw_data_[0] + 1
        else:
            next_id = 0

        return next_id

    def process_mailing_id(change_log_item):
        """TODO"""

        # check if this change_log record was somehow processed
        sql_text = sqlalchemy.text("""SELECT EXISTS (SELECT * FROM notif_mailings WHERE change_log_id=:a);""")
        record_was_processed_already = conn.execute(sql_text, a=change_log_item).fetchone()[0]

        # TODO: DEBUG
        if record_was_processed_already:
            logging.info('[comp_notif]: 2 MAILINGS for 1 CHANGE LOG RECORD identified')
        # TODO: DEBUG

        # record into SQL table notif_mailings
        sql_text = sqlalchemy.text("""
                        INSERT INTO notif_mailings (topic_id, source_script, mailing_type, change_log_id)
                        VALUES (:a, :b, :c, :d)
                        RETURNING mailing_id;
                        """)
        raw_data = conn.execute(
            sql_text, a=topic_id, b='notifications_script', c=change_type, d=change_log_item
        ).fetchone()

        mail_id = raw_data[0]
        logging.info(f'mailing_id = {mail_id}')

        users_should_not_be_informed = get_from_sql_list_of_users_with_prepared_message(change_log_item)
        logging.info('users_who_should_not_be_informed:')
        logging.info(users_should_not_be_informed)
        logging.info('in total ' + str(len(users_should_not_be_informed)))

        # TODO: do we need this table at all?
        # record into SQL table notif_mailings_status
        sql_text = sqlalchemy.text("""
                                            INSERT INTO notif_mailing_status (mailing_id, event, event_timestamp)
                                            VALUES (:a, :b, :c);
                                            """)
        conn.execute(sql_text, a=mail_id, b='created', c=datetime.datetime.now())

        return users_should_not_be_informed, record_was_processed_already, mail_id

    def check_if_age_requirements_met(search_ages, user_ages):
        """check if user wants to receive notifications for such age"""

        requirements_met = False

        if not user_ages or not search_ages:
            return True

        for age_rage in user_ages:
            user_age_range_start = age_rage[0]
            user_age_range_finish = age_rage[1]

            for i in range(user_age_range_start, user_age_range_finish + 1):
                for j in range(search_ages[0], search_ages[1] + 1):
                    if i == j:
                        requirements_met = True
                        break
                else:
                    continue
                break

        return requirements_met

    def crop_user_list(users_list_incoming, users_should_not_be_informed, record):
        """crop user_list to only affected users"""

        users_list_outcome = users_list_incoming

        # 1. INFORG 2X notifications. crop the list of users, excluding Users who receives all types of notifications
        # (otherwise it will be doubling for them)
        temp_user_list = []
        if record.change_type != 4:
            logging.info(f'User List crop due to Inforg 2x: {len(users_list_outcome)} --> {len(users_list_outcome)}')
        else:
            for user_line in users_list_outcome:
                # if this record is about inforg_comments and user already subscribed to all comments
                if not user_line.all_notifs:
                    temp_user_list.append(user_line)
                    logging.info(
                        f'Inforg 2x CHECK for {user_line.user_id} is OK, record {record.change_type}, '
                        f'user {user_line.user_id} {user_line.all_notifs}. '
                        f'record {record.forum_search_num}'
                    )
                else:
                    logging.info(
                        f'Inforg 2x CHECK for {user_line.user_id} is FAILED, record {record.change_type}, '
                        f'user {user_line.user_id} {user_line.all_notifs}. '
                        f'record {record.forum_search_num}'
                    )
            logging.info(f'User List crop due to Inforg 2x: {len(users_list_outcome)} --> {len(temp_user_list)}')
            users_list_outcome = temp_user_list

        # 2. AGES. crop the list of users, excluding Users who does not want to receive notifications for such Ages
        temp_user_list = []
        if not (record.age_min or record.age_max):
            logging.info('User List crop due to ages: no changes, there were no age_min and max for search')
            return users_list_outcome

        search_age_range = [record.age_min, record.age_max]

        for user_line in users_list_outcome:
            user_age_ranges = user_line.age_periods
            age_requirements_met = check_if_age_requirements_met(search_age_range, user_age_ranges)
            if age_requirements_met:
                temp_user_list.append(user_line)
                logging.info(
                    f'AGE CHECK for {user_line.user_id} is OK, record {search_age_range}, '
                    f'user {user_age_ranges}. record {record.forum_search_num}'
                )
            else:
                logging.info(
                    f'AGE CHECK for {user_line.user_id} is FAIL, record {search_age_range}, '
                    f'user {user_age_ranges}. record {record.forum_search_num}'
                )

        logging.info(f'User List crop due to ages: {len(users_list_outcome)} --> {len(temp_user_list)}')
        users_list_outcome = temp_user_list

        # 3. RADIUS. crop the list of users, excluding Users who does want to receive notifications within the radius
        try:
            search_lat = record.search_latitude
            search_lon = record.search_longitude
            list_of_city_coords = None
            if record.city_locations and record.city_locations != 'None':
                non_geolocated = [x for x in eval(record.city_locations) if isinstance(x, str)]
                list_of_city_coords = eval(record.city_locations) if not non_geolocated else None

            temp_user_list = []

            # CASE 3.1. When exact coordinates of Search Headquarters are indicated
            if search_lat and search_lon:
                for user_line in users_list_outcome:
                    if not (user_line.radius and user_line.user_latitude and user_line.user_longitude):
                        temp_user_list.append(user_line)
                        continue
                    user_lat = user_line.user_latitude
                    user_lon = user_line.user_longitude
                    actual_distance, direction = define_dist_and_dir_to_search(
                        search_lat, search_lon, user_lat, user_lon
                    )
                    actual_distance = int(actual_distance)
                    if actual_distance <= user_line.radius:
                        temp_user_list.append(user_line)

            # CASE 3.2. When exact coordinates of a Place are geolocated
            elif list_of_city_coords:
                for user_line in users_list_outcome:
                    if not (user_line.radius and user_line.user_latitude and user_line.user_longitude):
                        temp_user_list.append(user_line)
                        continue
                    user_lat = user_line.user_latitude
                    user_lon = user_line.user_longitude

                    for city_coords in list_of_city_coords:
                        search_lat, search_lon = city_coords
                        actual_distance, direction = define_dist_and_dir_to_search(
                            search_lat, search_lon, user_lat, user_lon
                        )
                        actual_distance = int(actual_distance)
                        if actual_distance <= user_line.radius:
                            temp_user_list.append(user_line)
                            break

            # CASE 3.3. No coordinates available
            else:
                temp_user_list = users_list_outcome

            logging.info(f'User List crop due to radius: {len(users_list_outcome)} --> {len(temp_user_list)}')
            users_list_outcome = temp_user_list

        except Exception as e:
            logging.info(f'TEMP - exception radius: {repr(e)}')
            logging.exception(e)

        # 4. DOUBLING. crop the list of users, excluding Users who were already notified on this change_log_id
        temp_user_list = []
        for user_line in users_list_outcome:
            if user_line.user_id not in users_should_not_be_informed:
                temp_user_list.append(user_line)
        logging.info(f'User List crop due to doubling: {len(users_list_outcome)} --> {len(temp_user_list)}')
        users_list_outcome = temp_user_list

        # 5. FOLLOW SEARCH. crop the list of users, excluding Users who is not following this search
        logging.info(f'Crop user list step 5: forum_search_num=={record.forum_search_num}')
        try:
            temp_user_list = []
            sql_text_ = sqlalchemy.text("""
            SELECT u.user_id FROM users u
            LEFT JOIN user_pref_search_filtering upsf ON upsf.user_id=u.user_id and 'whitelist' = ANY(upsf.filter_name)
            WHERE upsf.filter_name is not null AND NOT
            (
                (	exists(select 1 from user_pref_search_whitelist upswls
                        JOIN searches s ON search_forum_num=upswls.search_id 
                        WHERE upswls.user_id=u.user_id and upswls.search_id != :a and upswls.search_following_mode=:b
                        and s.status != 'СТОП')
					AND
					not exists(select 1 from user_pref_search_whitelist upswls WHERE upswls.user_id=u.user_id and upswls.search_id = :a and upswls.search_following_mode=:b)
				) 
				OR
                exists(select 1 from user_pref_search_whitelist upswls WHERE upswls.user_id=u.user_id and upswls.search_id = :a and upswls.search_following_mode=:c)
            )
            OR upsf.filter_name is null
            ;
            """)
            rows = conn.execute(sql_text_, a=record.forum_search_num, b='👀 ', c='❌ ').fetchall()
            logging.info(f'Crop user list step 5: len(rows)=={len(rows)}')

            users_following = []
            for row in rows:
                users_following.append(row[0])

            temp_user_list = []
            for user_line in users_list_outcome:
                if user_line.user_id in users_following:
                    temp_user_list.append(user_line)

            logging.info(
                f'Crop user list step 5: User List crop due to whitelisting: {len(users_list_outcome)} --> {len(temp_user_list)}'
            )
            # if len(users_list_outcome) - len(temp_user_list) <=20:
            #     logging.info(f'Crop user list step 5: cropped users: {users_list_outcome - temp_user_list}')
            users_list_outcome = temp_user_list
        except Exception as ee:
            logging.info('exception happened')
            logging.exception(ee)

        return users_list_outcome

    global stat_list_of_recipients

    stat_list_of_recipients = []  # still not clear why w/o it – saves data from prev iterations
    number_of_situations_checked = 0
    number_of_messages_sent = 0
    cleaner = re.compile('<.*?>')

    try:
        # skip ignored lines which don't require a notification
        if new_record.ignore == 'y':
            new_record.processed = 'yes'
            logging.info('Iterations over all Users and Updates are done (record Ignored)')
            return new_record

        s_lat = new_record.search_latitude
        s_lon = new_record.search_longitude
        topic_id = new_record.forum_search_num
        change_type = new_record.change_type
        change_log_id = new_record.change_id
        topic_type_id = new_record.topic_type_id

        users_who_should_not_be_informed, this_record_was_processed_already, mailing_id = process_mailing_id(
            change_log_id
        )

        list_of_users = crop_user_list(list_of_users, users_who_should_not_be_informed, new_record)

        message_for_pubsub = {'triggered_by_func_id': function_id, 'text': 'initiate notifs send out'}
        publish_to_pubsub('topic_to_send_notifications', message_for_pubsub)

        for user in list_of_users:
            u_lat = user.user_latitude
            u_lon = user.user_longitude
            region_to_show = new_record.region if user.user_in_multi_folders else None
            message = ''
            number_of_situations_checked += 1

            # start composing individual messages (specific user on specific situation)
            if change_type == 0:  # new topic: new search, new event
                num_of_msgs_sent_already = user.user_new_search_notifs

                if topic_type_id in {0, 1, 2, 3, 4, 5}:  # if it's a new search
                    message = compose_individual_message_on_new_search(
                        new_record, s_lat, s_lon, u_lat, u_lon, region_to_show, num_of_msgs_sent_already
                    )
                else:  # new event
                    message = new_record.message[0]

            elif change_type == 1 and topic_type_id in {0, 1, 2, 3, 4, 5}:  # search status change
                message = new_record.message[0]
                if user.user_in_multi_folders and new_record.message[1]:
                    message += new_record.message[1]

            elif change_type == 2:  # 'title_change':
                message = new_record.message

            elif change_type == 3:  # 'replies_num_change':
                message = new_record.message[0]

            elif change_type == 4:  # 'inforg_replies':
                message = new_record.message[0]
                if user.user_in_multi_folders and new_record.message[1]:
                    message += new_record.message[1]
                if new_record.message[2]:
                    message += new_record.message[2]

            elif change_type == 8:  # first_post_change
                message = compose_individual_message_on_first_post_change(new_record, region_to_show)

            # TODO: to delete msg_group at all ?
            # messages followed by coordinates (sendMessage + sendLocation) have same group
            msg_group_id = get_the_new_group_id() if change_type in {0, 8} else None
            # not None for new_search, field_trips_new, field_trips_change,  coord_change

            # define if user received this message already
            this_user_was_notified = False

            if this_record_was_processed_already:
                this_user_was_notified = get_from_sql_if_was_notified_already(
                    user.user_id, 'text', new_record.change_id
                )

                logging.info(f'this user was notified already {user.user_id}, {this_user_was_notified}')
                if user.user_id in users_who_should_not_be_informed:
                    logging.info('this user is in the list of non-notifiers')
                else:
                    logging.info('this user is NOT in the list of non-notifiers')

            if message and not this_user_was_notified:
                # TODO: make text more compact within 50 symbols
                message_without_html = re.sub(cleaner, '', message)

                message_params = {'parse_mode': 'HTML', 'disable_web_page_preview': 'True'}

                # for the new searches we add a link to web_app map
                if change_type == 0:
                    map_button = {'text': 'Смотреть на Карте Поисков', 'web_app': {'url': get_secrets('web_app_url')}}
                    message_params['reply_markup'] = {'inline_keyboard': [[map_button]]}

                # TODO: Debug only - to delete
                print(
                    f'what we are saving to SQL: {mailing_id}, {user.user_id}, {message_without_html}, '
                    f'{message_params}, {msg_group_id}, {change_log_id}'
                )
                # TODO: Debug only - to delete

                # record into SQL table notif_by_user
                save_to_sql_notif_by_user(
                    mailing_id,
                    user.user_id,
                    message,
                    message_without_html,
                    'text',
                    message_params,
                    msg_group_id,
                    change_log_id,
                )

                # for user tips in "new search" notifs – to increase sent messages counter
                if change_type == 0 and topic_type_id in {0, 1, 2, 3, 4, 5}:  # 'new_search':
                    stat_list_of_recipients.append(user.user_id)

                # save to SQL the sendLocation notification for "new search"
                if change_type in {0} and topic_type_id in {0, 1, 2, 3, 4, 5} and s_lat and s_lon:
                    # 'new_search',
                    message_params = {'latitude': s_lat, 'longitude': s_lon}

                    # record into SQL table notif_by_user (not text, but coords only)
                    save_to_sql_notif_by_user(
                        mailing_id, user.user_id, None, None, 'coords', message_params, msg_group_id, change_log_id
                    )
                if change_type == 8:
                    try:
                        list_of_coords = re.findall(r'<code>', message)
                        if list_of_coords and len(list_of_coords) == 1:
                            # that would mean that there's only 1 set of new coordinates and hence we can
                            # send the dedicated sendLocation message
                            both_coordinates = re.search(r'(?<=<code>).{5,100}(?=</code>)', message).group()
                            if both_coordinates:
                                new_lat = re.search(r'^[\d.]{2,12}(?=\D)', both_coordinates).group()
                                new_lon = re.search(r'(?<=\D)[\d.]{2,12}$', both_coordinates).group()
                                message_params = {'latitude': new_lat, 'longitude': new_lon}
                                save_to_sql_notif_by_user(
                                    mailing_id,
                                    user.user_id,
                                    None,
                                    None,
                                    'coords',
                                    message_params,
                                    msg_group_id,
                                    change_log_id,
                                )
                    except Exception as ee:
                        logging.info('exception happened')
                        logging.exception(ee)

                number_of_messages_sent += 1

        # mark this line as all-processed
        new_record.processed = 'yes'
        logging.info('Iterations over all Users and Updates are done')

    except Exception as e1:
        logging.info('Not able to Iterate over all Users and Updates: ')
        logging.exception(e1)

    return new_record


def generate_yandex_maps_place_link2(lat, lon, param):
    """generate a link to yandex map with lat/lon"""

    display = 'Карта' if param == 'map' else param
    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

    return msg


def compose_individual_message_on_new_search(new_record, s_lat, s_lon, u_lat, u_lon, region_to_show, num_of_sent):
    """compose individual message for notification of every user on new search"""

    place_link = ''
    clickable_coords = ''
    tip_on_click_to_copy = ''
    tip_on_home_coords = ''

    region_wording = f' в регионе {region_to_show}' if region_to_show else ''

    # 0. Heading and Region clause if user is 'multi-regional'
    message = f'{new_record.topic_emoji}Новый поиск{region_wording}!\n'

    # 1. Search important attributes - common part (e.g. 'Внимание, выезд!)
    if new_record.message[1]:
        message += new_record.message[1]

    # 2. Person (e.g. 'Иванов 60' )
    message += '\n' + new_record.message[0]

    # 3. Dist & Dir – individual part for every user
    if s_lat and s_lon and u_lat and u_lon:
        try:
            dist, direct = define_dist_and_dir_to_search(s_lat, s_lon, u_lat, u_lon)
            dist = int(dist)
            direction = f'\n\nОт вас ~{dist} км {direct}'

            message += generate_yandex_maps_place_link2(s_lat, s_lon, direction)
            message += f'\n<code>{coord_format.format(float(s_lat))}, ' f'{coord_format.format(float(s_lon))}</code>'

        except Exception as e:
            logging.info(
                f'Not able to compose individual msg with distance & direction, params: '
                f'[{new_record}, {s_lat}, {s_lon}, {u_lat}, {u_lon}]'
            )
            logging.exception(e)

    if s_lat and s_lon and not u_lat and not u_lon:
        try:
            message += '\n\n' + generate_yandex_maps_place_link2(s_lat, s_lon, 'map')

        except Exception as e:
            logging.info(
                f'Not able to compose message with Yandex Map Link, params: '
                f'[{new_record}, {s_lat}, {s_lon}, {u_lat}, {u_lon}]'
            )
            logging.exception(e)

    # 4. Managers – common part
    if new_record.message[2]:
        message += '\n\n' + new_record.message[2]

    message += '\n\n'

    # 5. Tips and Suggestions
    if not num_of_sent or num_of_sent in fib_list:
        if s_lat and s_lon:
            message += '<i>Совет: Координаты и телефоны можно скопировать, нажав на них.</i>\n'

        if s_lat and s_lon and not u_lat and not u_lon:
            message += (
                '<i>Совет: Чтобы Бот показывал Направление и Расстояние до поиска – просто укажите ваши '
                '"Домашние координаты" в Настройках Бота.</i>'
            )

    if s_lat and s_lon:
        clickable_coords = f'<code>{coord_format.format(float(s_lat))}, {coord_format.format(float(s_lon))}</code>'
        if u_lat and u_lon:
            dist, direct = define_dist_and_dir_to_search(s_lat, s_lon, u_lat, u_lon)
            dist = int(dist)
            place = f'От вас ~{dist} км {direct}'
        else:
            place = 'Карта'
        place_link = f'<a href="https://yandex.ru/maps/?pt={s_lon},{s_lat}&z=11&l=map">{place}</a>'

        if not num_of_sent or num_of_sent in fib_list:
            tip_on_click_to_copy = '<i>Совет: Координаты и телефоны можно скопировать, нажав на них.</i>'
            if not u_lat and not u_lon:
                tip_on_home_coords = (
                    '<i>Совет: Чтобы Бот показывал Направление и Расстояние до поиска – просто '
                    'укажите ваши "Домашние координаты" в Настройках Бота.</i>'
                )

    # TODO - yet not implemented new message template
    obj = new_record.message_object
    final_message = f"""{new_record.topic_emoji}Новый поиск{region_wording}!\n
                        {obj.activities}\n\n
                        {obj.clickable_name}\n\n
                        {place_link}\n
                        {clickable_coords}\n\n
                        {obj.managers}\n\n
                        {tip_on_click_to_copy}\n\n
                        {tip_on_home_coords}"""

    final_message = re.sub(r'\s{3,}', '\n\n', final_message)  # clean excessive blank lines
    final_message = re.sub(r'\s*$', '', final_message)  # clean blank symbols in the end of file
    logging.info(f'OLD - FINAL NEW MESSAGE FOR NEW SEARCH: {message}')
    logging.info(f'NEW - FINAL NEW MESSAGE FOR NEW SEARCH: {final_message}')
    # TODO ^^^

    return message


def compose_individual_message_on_first_post_change(new_record, region_to_show):
    """compose individual message for notification of every user on change of first post"""

    message = new_record.message
    region = f' ({region_to_show})' if region_to_show else ''
    message = message.format(region=region)

    return message


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

    global project_id

    topic_path = publisher.topic_path(project_id, topic_name)
    message_json = json.dumps(
        {
            'data': {'message': message},
        }
    )
    message_bytes = message_json.encode('utf-8')

    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info(f'Sent pub/sub message: {message}')

    except Exception as e:
        logging.info('Not able to send pub/sub message: ')
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


def mark_new_record_as_processed(conn, new_record):
    """mark all the new records in SQL as processed, to avoid processing in the next iteration"""

    try:
        if new_record.processed == 'yes':
            if new_record.ignore != 'y':
                sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'y' WHERE id=:a;""")
                conn.execute(sql_text, a=new_record.change_id)
                logging.info(f'The New Record {new_record.change_id} was marked as processed in PSQL')
            else:
                sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'n' WHERE id=:a;""")
                conn.execute(sql_text, a=new_record.change_id)
                logging.info(f'The New Record {new_record.change_id} was marked as IGNORED in PSQL')

        logging.info('All Updates are marked as processed in Change Log')

    except Exception as e:
        # FIXME – should be a smarter way to re-process the record instead of just marking everything as processed
        # For Safety's Sake – Update Change_log SQL table, setting 'y' everywhere
        conn.execute(
            """UPDATE change_log SET notification_sent = 'y' WHERE notification_sent is NULL
            OR notification_sent='s';"""
        )

        logging.info('Not able to mark Updates as Processed in Change Log')
        logging.exception(e)
        logging.info('Due to error, all Updates are marked as processed in Change Log')
        notify_admin('ERROR: Not able to mark Updates as Processed in Change Log!')
        # FIXME ^^^

    return None


def mark_new_comments_as_processed(conn, record):
    """mark in SQL table Comments all the comments that were processed at this step, basing on search_forum_id"""

    try:
        # TODO – is it correct that we mark comments processes for any Comments for certain search? Looks
        #  like we can mark some comments which are not yet processed at all. Probably base on change_id? To be checked
        if record.processed == 'yes' and record.ignore != 'y':
            if record.change_type == 3:
                sql_text = sqlalchemy.text("UPDATE comments SET notification_sent = 'y' WHERE search_forum_num=:a;")
                conn.execute(sql_text, a=record.forum_search_num)

            elif record.change_type == 4:
                sql_text = sqlalchemy.text("UPDATE comments SET notif_sent_inforg = 'y' WHERE search_forum_num=:a;")
                conn.execute(sql_text, a=record.forum_search_num)
            # FIXME ^^^

            logging.info(f'The Update {record.change_id} with Comments that are processed and not ignored')
            logging.info('All Comments are marked as processed')

    except Exception as e:
        # TODO – seems a vary vague solution: to mark all
        sql_text = sqlalchemy.text("""UPDATE comments SET notification_sent = 'y' WHERE notification_sent is Null
                                      OR notification_sent = 's';""")
        conn.execute(sql_text)
        sql_text = sqlalchemy.text("""UPDATE comments SET notif_sent_inforg = 'y' WHERE notif_sent_inforg is Null;""")
        conn.execute(sql_text)

        logging.info('Not able to mark Comments as Processed:')
        logging.exception(e)
        logging.info('Due to error, all Comments are marked as processed')
        notify_admin('ERROR: Not able to mark Comments as Processed!')
        # TODO ^^^

    return None


def check_and_save_event_id(context, event, conn, new_record, function_id, triggered_by_func_id):
    """Work with PSQL table functions_registry. Goal of the table & function is to avoid parallel work of
    two compose_notifications functions. Executed in the beginning and in the end of compose_notifications function"""

    def check_if_other_functions_are_working():
        """Check in PSQL in there's the same function 'compose_notifications' working in parallel"""

        sql_text_psy = sqlalchemy.text("""
                        SELECT event_id
                        FROM functions_registry
                        WHERE
                            time_start > NOW() - interval '130 seconds' AND
                            time_finish IS NULL AND
                            cloud_function_name  = 'compose_notifications'
                        /*action='check_if_there_is_parallel_compose_function' */;""")

        lines = conn.execute(sql_text_psy).fetchone()

        parallel_functions = True if lines else False

        return parallel_functions

    def record_start_of_function(event_num, function_num):
        """Record into PSQL that this function started working (id = id of the respective pub/sub event)"""

        sql_text_psy = sqlalchemy.text("""INSERT INTO functions_registry
                                          (event_id, time_start, cloud_function_name, function_id, triggered_by_func_id)
                                          VALUES (:a, :b, :c, :d, :e)
                                          /*action='save_start_of_compose_function' */;""")

        conn.execute(
            sql_text_psy,
            a=event_num,
            b=datetime.datetime.now(),
            c='compose_notifications',
            d=function_num,
            e=triggered_by_func_id,
        )
        logging.info(f'function was triggered by event {event_num}')

        return None

    def record_finish_of_function(event_num, params_json):
        """Record into PSQL that this function finished working (id = id of the respective pub/sub event)"""

        sql_text_psy = sqlalchemy.text("""UPDATE functions_registry
                                          SET time_finish = :a, params = :c
                                          WHERE event_id = :b
                                          /*action='save_finish_of_compose_function' */;""")

        conn.execute(sql_text_psy, a=datetime.datetime.now(), b=event_num, c=params_json)

        return None

    if not context or not event:
        return False

    try:
        event_id = context.event_id
    except Exception as e:  # noqa
        return False

    # if this functions is triggered in the very beginning of the Google Cloud Function execution
    if event == 'start':
        if check_if_other_functions_are_working():
            record_start_of_function(event_id, function_id)
            return True

        record_start_of_function(event_id, function_id)
        return False

    # if this functions is triggered in the very end of the Google Cloud Function execution
    elif event == 'finish':
        json_of_params = None
        if new_record:
            # FIXME -- temp try. the content is not temp
            try:
                list_of_change_log_ids = [new_record.change_id]
                json_of_params = json.dumps({'ch_id': list_of_change_log_ids})
            except Exception as e:  # noqa
                logging.exception(e)
            # FIXME ^^^
        record_finish_of_function(event_id, json_of_params)
        return False


def check_if_need_compose_more(conn, function_id):
    """check if there are any notifications remained to be composed"""

    check = conn.execute("""SELECT search_forum_num, changed_field, new_value, id, change_type FROM change_log
                            WHERE notification_sent is NULL
                            OR notification_sent='s' LIMIT 1; """).fetchall()
    if check:
        logging.info('we checked – there is still something to compose: re-initiating [compose_notification]')
        message_for_pubsub = {'triggered_by_func_id': function_id, 'text': 're-run from same script'}
        publish_to_pubsub('topic_for_notification', message_for_pubsub)
    else:
        logging.info('we checked – there is nothing to compose: we are not re-initiating [compose_notification]')

    return None


def generate_random_function_id():
    """generates a random ID for every function – to track all function dependencies (no built-in ID in GCF)"""

    random_id = random.randint(100000000000, 999999999999)

    return random_id


def get_triggering_function(message_from_pubsub):
    """get a function_id of the function, which triggered this function (if available)"""

    triggered_by_func_id = None
    try:
        if (
            message_from_pubsub
            and isinstance(message_from_pubsub, dict)
            and 'triggered_by_func_id' in message_from_pubsub.keys()
        ):
            triggered_by_func_id = message_from_pubsub['triggered_by_func_id']

    except Exception as e:
        logging.exception(e)

    if triggered_by_func_id:
        logging.info(f'this function is triggered by func_id {triggered_by_func_id}')
    else:
        logging.info('triggering func_id was not determined')

    return triggered_by_func_id


def delete_ended_search_following(conn, new_record):  # issue425
    ### Delete from user_pref_search_whitelist if the search goes to one of ending statuses

    if new_record.change_type == 1 and new_record.status in ['Завершен', 'НЖ', 'НП', 'Найден']:
        stmt = sqlalchemy.text("""DELETE FROM user_pref_search_whitelist WHERE search_id=:a;""")
        conn.execute(stmt, a=new_record.forum_search_num)
        logging.info(
            f'Search id={new_record.forum_search_num} with status {new_record.status} is been deleted from user_pref_search_whitelist.'
        )
    return None


def main(event, context):  # noqa
    """key function which is initiated by Pub/Sub"""

    analytics_start_of_func = datetime.datetime.now()

    function_id = generate_random_function_id()
    message_from_pubsub = process_pubsub_message(event)
    triggered_by_func_id = get_triggering_function(message_from_pubsub)

    pool = sql_connect()
    with pool.connect() as conn:
        there_is_function_working_in_parallel = check_and_save_event_id(
            context, 'start', conn, None, function_id, triggered_by_func_id
        )
        if there_is_function_working_in_parallel:
            logging.info('function execution stopped due to parallel run with another function')
            check_and_save_event_id(context, 'finish', conn, None, function_id, triggered_by_func_id)
            logging.info('script finished')
            conn.close()
            pool.dispose()
            return None

        # compose New Records List: the delta from Change log
        new_record = compose_new_records_from_change_log(conn)

        # only if there are updates in Change Log
        if new_record:
            delete_ended_search_following(conn, new_record)  # issue425
            # enrich New Records List with all the updates that should be in notifications
            new_record = enrich_new_record_from_searches(conn, new_record)
            new_record = enrich_new_record_with_search_activities(conn, new_record)
            new_record = enrich_new_record_with_managers(conn, new_record)
            new_record = enrich_new_record_with_comments(conn, 'all', new_record)
            new_record = enrich_new_record_with_comments(conn, 'inforg', new_record)
            new_record = enrich_new_record_with_clickable_name(new_record)
            new_record = enrich_new_record_with_emoji(new_record)
            new_record = enrich_new_record_with_com_message_texts(new_record)

            # compose Users List: all the notifications recipients' details
            admins_list, testers_list = get_list_of_admins_and_testers(conn)  # for debug purposes
            list_of_users = compose_users_list_from_users(conn, new_record)
            list_of_users = enrich_users_list_with_age_periods(conn, list_of_users)
            list_of_users = enrich_users_list_with_radius(conn, list_of_users)

            analytics_match_finish = datetime.datetime.now()
            duration_match = round((analytics_match_finish - analytics_start_of_func).total_seconds(), 2)
            logging.info(f'time: function match end-to-end – {duration_match} sec')

            # check the matrix: new update - user and initiate sending notifications
            new_record = iterate_over_all_users(conn, admins_list, new_record, list_of_users, function_id)

            analytics_iterations_finish = datetime.datetime.now()
            duration_iterations = round((analytics_iterations_finish - analytics_match_finish).total_seconds(), 2)
            logging.info(f'time: function iterations end-to-end – {duration_iterations} sec')

            # mark all the "new" lines in tables Change Log & Comments as "old"
            mark_new_record_as_processed(conn, new_record)
            mark_new_comments_as_processed(conn, new_record)

            # final step – update statistics on how many users received notifications on new searches
            record_notification_statistics(conn)

        check_if_need_compose_more(conn, function_id)
        check_and_save_event_id(context, 'finish', conn, new_record, function_id, triggered_by_func_id)

        analytics_finish = datetime.datetime.now()
        if new_record:
            duration_saving = round((analytics_finish - analytics_iterations_finish).total_seconds(), 2)
            logging.info(f'time: function data saving – {duration_saving} sec')

        duration_full = round((analytics_finish - analytics_start_of_func).total_seconds(), 2)
        logging.info(f'time: function full end-to-end – {duration_full} sec')

        logging.info('script finished')

        conn.close()
    pool.dispose()

    return None
