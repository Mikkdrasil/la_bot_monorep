import ast
import datetime
import logging
import math
import re

import sqlalchemy
import sqlalchemy.connectors
import sqlalchemy.ext
import sqlalchemy.pool
from sqlalchemy.engine.base import Connection

from _dependencies.misc import age_writer, notify_admin

from .notif_common import (
    COORD_FORMAT,
    COORD_PATTERN,
    WINDOW_FOR_NOTIFICATIONS_DAYS,
    Comment,
    LineInChangeLog,
    MessageNewTopic,
    User,
)


def enrich_new_record_with_emoji(line: LineInChangeLog) -> None:
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


def enrich_new_record_with_clickable_name(line: LineInChangeLog) -> None:
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


def get_coords_from_list(input_list):
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


def compose_com_msg_on_first_post_change(record: LineInChangeLog) -> str:
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
                    updated_line = re.sub(COORD_PATTERN, '<code>\g<0></code>', line)
                    message += f'{updated_line}\n'
        else:
            message = message_dict['message']

    coord_change_phrase = ''
    add_lat, add_lon = get_coords_from_list(list_of_additions)
    del_lat, del_lon = get_coords_from_list(list_of_deletions)

    if old_lat and old_lon:
        old_lat = COORD_FORMAT.format(float(old_lat))
        old_lon = COORD_FORMAT.format(float(old_lon))

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


def compose_com_msg_on_inforg_comments(line: LineInChangeLog):
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


def compose_com_msg_on_new_comments(line: LineInChangeLog):
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


def add_tel_link(incoming_text: str, modifier: str = 'all') -> str:
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


def compose_com_msg_on_new_topic(line: LineInChangeLog):
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


def compose_com_msg_on_status_change(line: LineInChangeLog):
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


def compose_com_msg_on_title_change(line: LineInChangeLog):
    """compose the common, user-independent message on search title change"""

    activity = 'мероприятия' if line.topic_type_id == 10 else 'поиска'
    msg = f'{line.title} – обновление заголовка {activity} по {line.clickable_name}'

    return msg


def enrich_new_record_with_com_message_texts(line: LineInChangeLog) -> None:
    """add user-independent message text to the New Records"""

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


def enrich_users_list_with_age_periods(conn: sqlalchemy.engine.Connection, list_of_users: list[User]) -> None:
    """add the data on Lost people age notification preferences from user_pref_age into users List"""

    try:
        notif_prefs = conn.execute("""SELECT user_id, period_min, period_max FROM user_pref_age;""").fetchall()

        if not notif_prefs:
            return

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


def enrich_users_list_with_radius(conn: sqlalchemy.engine.Connection, list_of_users: list[User]) -> None:
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


def define_family_name(title_string: str, predefined_fam_name: str | None) -> str:
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


def enrich_new_record_from_searches(conn: Connection, r_line: LineInChangeLog) -> None:
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
            return

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


def enrich_new_record_with_search_activities(conn: Connection, r_line: LineInChangeLog) -> None:
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


def enrich_new_record_with_managers(conn: Connection, r_line: LineInChangeLog) -> None:
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


def enrich_new_record_with_comments(conn: Connection, type_of_comments, r_line: LineInChangeLog) -> None:
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
