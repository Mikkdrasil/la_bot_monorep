import datetime
import logging
import math
from typing import List, Tuple, Union

from psycopg2.extensions import cursor

from _dependencies.commons import Topics, publish_to_pubsub
from _dependencies.misc import age_writer, time_counter_since_search_start

from .schemas import SearchSummary


# TODO separate db functions and others
def save_user_pref_urgency(
    cur, user_id, urgency_value, b_pref_urgency_highest, b_pref_urgency_high, b_pref_urgency_medium, b_pref_urgency_low
):
    """save user urgency"""

    urgency_dict = {
        b_pref_urgency_highest: {'pref_id': 0, 'pref_name': 'highest'},
        b_pref_urgency_high: {'pref_id': 1, 'pref_name': 'high'},
        b_pref_urgency_medium: {'pref_id': 2, 'pref_name': 'medium'},
        b_pref_urgency_low: {'pref_id': 3, 'pref_name': 'low'},
    }

    try:
        pref_id = urgency_dict[urgency_value]['pref_id']
        pref_name = urgency_dict[urgency_value]['pref_name']
    except:  # noqa
        pref_id = 99
        pref_name = 'unidentified'

    cur.execute("""DELETE FROM user_pref_urgency WHERE user_id=%s;""", (user_id,))
    cur.execute(
        """INSERT INTO user_pref_urgency (user_id, pref_id, pref_name, timestamp) VALUES (%s, %s, %s, %s);""",
        (user_id, pref_id, pref_name, datetime.datetime.now()),
    )

    logging.info(f'urgency set as {pref_name} for user_id {user_id}')

    return None


def save_user_coordinates(cur: cursor, user_id: int, input_latitude: float, input_longitude: float) -> None:
    """Save / update user "home" coordinates"""

    cur.execute('DELETE FROM user_coordinates WHERE user_id=%s;', (user_id,))

    now = datetime.datetime.now()
    cur.execute(
        """INSERT INTO user_coordinates (user_id, latitude, longitude, upd_time) values (%s, %s, %s, %s);""",
        (user_id, input_latitude, input_longitude, now),
    )

    return None


def show_user_coordinates(cur: cursor, user_id: int) -> Tuple[str, str]:
    """Return the saved user "home" coordinates"""

    cur.execute("""SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;""", (user_id,))

    try:
        lat, lon = list(cur.fetchone())
    except:  # noqa
        lat = None
        lon = None

    return lat, lon


def delete_user_coordinates(cur: cursor, user_id: int) -> None:
    """Delete the saved user "home" coordinates"""

    cur.execute('DELETE FROM user_coordinates WHERE user_id=%s;', (user_id,))

    return None


def distance_to_search(search_lat, search_lon, user_let, user_lon, coded_style=True):
    """Return the distance and direction from user "home" coordinates to the search coordinates"""

    r = 6373.0  # radius of the Earth

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

    distance = r * c
    dist = round(distance)

    # define direction

    def calc_bearing(lat_2, lon_2, lat_1, lon_1):
        d_lon_ = lon_2 - lon_1
        x = math.cos(math.radians(lat_2)) * math.sin(math.radians(d_lon_))
        y = math.cos(math.radians(lat_1)) * math.sin(math.radians(lat_2)) - math.sin(math.radians(lat_1)) * math.cos(
            math.radians(lat_2)
        ) * math.cos(math.radians(d_lon_))
        bearing = math.atan2(x, y)
        bearing = math.degrees(bearing)

        return bearing

    def calc_nsew(lat_1, lon_1, lat_2, lon_2, coded_style=True):
        # indicators of the direction, like ↖︎
        if coded_style:
            points = [
                '&#8593;&#xFE0E;',
                '&#8599;&#xFE0F;',
                '&#8594;&#xFE0E;',
                '&#8600;&#xFE0E;',
                '&#8595;&#xFE0E;',
                '&#8601;&#xFE0E;',
                '&#8592;&#xFE0E;',
                '&#8598;&#xFE0E;',
            ]
        else:
            points = ['⬆️', '↗️', '➡️', '↘️', '⬇️', '↙️', '⬅️', '↖️']

        bearing = calc_bearing(lat_1, lon_1, lat_2, lon_2)
        bearing += 22.5
        bearing = bearing % 360
        bearing = int(bearing / 45)  # values 0 to 7
        nsew = points[bearing]

        return nsew

    direction = calc_nsew(lat1, lon1, lat2, lon2, coded_style)

    return [dist, direction]


def get_user_reg_folders_preferences(cur: cursor, user_id: int) -> List[int]:
    """Return user's regional preferences"""

    user_prefs_list = []

    try:
        cur.execute('SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=%s;', (user_id,))
        user_reg_prefs_array = cur.fetchall()

        for line in user_reg_prefs_array:
            user_prefs_list.append(line[0])

        logging.info(str(user_prefs_list))

    except Exception as e:
        logging.info(f'failed to get user regional prefs for user {user_id}')
        logging.exception(e)

    return user_prefs_list


def get_user_role(cur: cursor, user_id: int):
    """Return user's role"""

    user_role = None

    try:
        cur.execute('SELECT role FROM users WHERE user_id=%s LIMIT 1;', (user_id,))
        user_role = cur.fetchone()
        if user_role:
            user_role = user_role[0]

        logging.info(f'user {user_id} role is {user_role}')

    except Exception as e:
        logging.info(f'failed to get user role for user {user_id}')
        logging.exception(e)

    return user_role


def get_user_sys_roles(cur, user_id):
    """Return user's roles in system"""

    user_roles = ['']

    try:
        cur.execute('SELECT role FROM user_roles WHERE user_id=%s;', (user_id,))
        lines = cur.fetchall()
        for line in lines:
            user_roles.append(line[0])
        logging.info(f'user {user_id} role has roles {user_roles=}')
    except Exception as e:
        logging.info(f'failed to get from user_roles for user {user_id}')
        logging.exception(e)

    return user_roles


def add_user_sys_role(cur, user_id, sys_role_name):
    """Saves user's role in system"""

    try:
        cur.execute(
            """INSERT INTO user_roles (user_id, role) 
                    VALUES (%s, %s) ON CONFLICT DO NOTHING;""",
            (user_id, sys_role_name),
        )

    except Exception as e:
        logging.info(f'failed to insert into user_roles for user {user_id}')
        logging.exception(e)

    return None


def delete_user_sys_role(cur, user_id, sys_role_name):
    """Deletes user's role in system"""

    try:
        cur.execute(
            """DELETE FROM user_roles 
                    WHERE user_id=%s and role=%s;""",
            (user_id, sys_role_name),
        )

    except Exception as e:
        logging.info(f'failed to delete from user_roles for user {user_id}')
        logging.exception(e)

    return None


def save_preference(cur: cursor, user_id: int, preference: str):
    """Save user preference on types of notifications to be sent by bot"""

    # the master-table is dict_notif_types:

    pref_dict = {
        'topic_new': 0,
        'topic_status_change': 1,
        'topic_title_change': 2,
        'topic_comment_new': 3,
        'topic_inforg_comment_new': 4,
        'topic_field_trip_new': 5,
        'topic_field_trip_change': 6,
        'topic_coords_change': 7,
        'topic_first_post_change': 8,
        'bot_news': 20,
        'all': 30,
        'not_defined': 99,
        'new_searches': 0,
        'status_changes': 1,
        'title_changes': 2,
        'comments_changes': 3,
        'inforg_comments': 4,
        'field_trips_new': 5,
        'field_trips_change': 6,
        'coords_change': 7,
        'first_post_changes': 8,
    }

    def execute_insert(user: int, preference_name: str):
        """execute SQL INSERT command"""

        preference_id = pref_dict[preference_name]
        cur.execute(
            """INSERT INTO user_preferences 
                        (user_id, preference, pref_id) 
                        VALUES (%s, %s, %s) 
                        ON CONFLICT DO NOTHING;""",
            (user, preference_name, preference_id),
        )

        return None

    def execute_delete(user: int, list_of_prefs: List[str]):
        """execute SQL DELETE command"""

        if list_of_prefs:
            for line in list_of_prefs:
                line_id = pref_dict[line]
                cur.execute("""DELETE FROM user_preferences WHERE user_id=%s AND pref_id=%s;""", (user, line_id))
        else:
            cur.execute("""DELETE FROM user_preferences WHERE user_id=%s;""", (user,))

        return None

    def execute_check(user, pref_list):
        """execute SQL SELECT command and returns TRUE / FALSE if something found"""

        result = False

        for line in pref_list:
            cur.execute("""SELECT id FROM user_preferences WHERE user_id=%s AND preference=%s LIMIT 1;""", (user, line))

            if str(cur.fetchone()) != 'None':
                result = True
                break

        return result

    if preference == 'all':
        execute_delete(user_id, [])
        execute_insert(user_id, preference)

    elif preference in {'new_searches', 'status_changes', 'title_changes', 'comments_changes', 'first_post_changes'}:
        if execute_check(user_id, ['all']):
            execute_insert(user_id, 'bot_news')
        execute_delete(user_id, ['all'])

        execute_insert(user_id, preference)

        if preference == 'comments_changes':
            execute_delete(user_id, ['inforg_comments'])

    elif preference == 'inforg_comments':
        if not execute_check(user_id, ['all', 'comments_changes']):
            execute_insert(user_id, preference)

    elif preference in {'field_trips_new', 'field_trips_change', 'coords_change'}:
        # FIXME – temp deactivation unlit feature will be ready for prod
        # FIXME – to be added to "new_searches" etc group
        # if not execute_check(user_id, ['all']):
        execute_insert(user_id, preference)

    elif preference in {
        '-new_searches',
        '-status_changes',
        '-comments_changes',
        '-inforg_comments',
        '-title_changes',
        '-all',
        '-field_trips_new',
        '-field_trips_change',
        '-coords_change',
        '-first_post_changes',
    }:
        if preference == '-all':
            execute_insert(user_id, 'bot_news')
            execute_insert(user_id, 'new_searches')
            execute_insert(user_id, 'status_changes')
            execute_insert(user_id, 'inforg_comments')
            execute_insert(user_id, 'first_post_changes')
        elif preference == '-comments_changes':
            execute_insert(user_id, 'inforg_comments')

        preference = preference[1:]
        execute_delete(user_id, [preference])

    return None


def update_and_download_list_of_regions(
    cur: cursor, user_id: int, got_message: str, b_menu_set_region: str, b_fed_dist_pick_other: str
) -> str:
    """Upload, download and compose a message on the list of user's regions"""

    msg = ''
    is_first_entry = None
    region_was_in_db = None
    region_is_the_only = None

    fed_okr_dict = {
        'Дальневосточный ФО',
        'Приволжский ФО',
        'Северо-Кавказский ФО',
        'Северо-Западный ФО',
        'Сибирский ФО',
        'Уральский ФО',
        'Центральный ФО',
        'Южный ФО',
    }

    # upload the new regional setting
    folder_dict = {
        'Москва и МО: Активные Поиски': [276],
        'Москва и МО: Инфо Поддержка': [41],
        'Белгородская обл.': [236],
        'Брянская обл.': [138],
        'Владимирская обл.': [123, 233],
        'Воронежская обл.': [271, 315],
        'Ивановская обл.': [132, 193],
        'Калужская обл.': [185],
        'Костромская обл.': [151],
        'Курская обл.': [186],
        'Липецкая обл.': [272],
        'Орловская обл.': [222, 324],
        'Рязанская обл.': [155],
        'Смоленская обл.': [122],
        'Тамбовская обл.': [273],
        'Тверская обл.': [126],
        'Тульская обл.': [125],
        'Ярославская обл.': [264],
        'Прочие поиски по ЦФО': [179],
        'Адыгея': [299],
        'Астраханская обл.': [336],
        'Волгоградская обл.': [131],
        'Краснодарский край': [162],
        'Крым': [293],
        'Ростовская обл.': [157],
        'Прочие поиски по ЮФО': [180],
        'Архангельская обл.': [330],
        'Вологодская обл.': [370, 369, 368, 367],
        'Карелия': [403, 404],
        'Коми': [378, 377, 376],
        'Ленинградская обл.': [120, 300],
        'Мурманская обл.': [214, 371, 372, 373],
        'Псковская обл.': [210, 383, 382],
        'Прочие поиски по СЗФО': [181],
        'Амурская обл.': [390],
        'Бурятия': [274],
        'Приморский край': [298],
        'Хабаровский край': [154],
        'Прочие поиски по ДФО': [188],
        'Алтайский край': [161],
        'Иркутская обл.': [137, 387, 386, 303],
        'Кемеровская обл.': [202, 308],
        'Красноярский край': [269, 318],
        'Новосибирская обл.': [177, 310],
        'Омская обл.': [153, 314],
        'Томская обл.': [215, 401],
        'Хакасия': [402],
        'Прочие поиски по СФО': [182],
        'Свердловская обл.': [213],
        'Курганская обл.': [391, 392],
        'Тюменская обл.': [339],
        'Ханты-Мансийский АО': [338],
        'Челябинская обл.': [280],
        'Ямало-Ненецкий АО': [204],
        'Прочие поиски по УФО': [187],
        'Башкортостан': [191, 235],
        'Кировская обл.': [211, 275],
        'Марий Эл': [295, 297],
        'Мордовия': [294],
        'Нижегородская обл.': [121, 289],
        'Оренбургская обл.': [337],
        'Пензенская обл.': [170, 322],
        'Пермский край': [143, 325],
        'Самарская обл.': [333, 334, 305],
        'Саратовская обл.': [212],
        'Татарстан': [163, 231],
        'Удмуртия': [237, 239],
        'Ульяновская обл.': [290, 320],
        'Чувашия': [265, 327],
        'Прочие поиски по ПФО': [183],
        'Дагестан': [292],
        'Ставропольский край': [173],
        'Чечня': [291],
        'Кабардино-Балкария': [301],
        'Ингушетия': [422],
        'Северная Осетия': [423],
        'Прочие поиски по СКФО': [184],
        'Прочие поиски по РФ': [116],
    }

    # Reversed dict is needed on the last step
    rev_reg_dict = {value[0]: key for (key, value) in folder_dict.items()}

    # TODO - get the list of regions from PSQL
    # TODO ^^^

    # case for the first entry to the screen of Reg Settings
    if got_message == b_menu_set_region:
        is_first_entry = 'yes'
    elif got_message in fed_okr_dict or got_message == b_fed_dist_pick_other:
        pass
    else:
        try:
            list_of_regs_to_upload = folder_dict[got_message]

            # any region
            cur.execute("""SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,))

            user_curr_regs_temp = cur.fetchall()
            user_curr_regs = [reg[0] for reg in user_curr_regs_temp]

            for user_reg in user_curr_regs:
                if list_of_regs_to_upload[0] == user_reg:
                    region_was_in_db = 'yes'
                    break
            if region_was_in_db:
                if len(user_curr_regs) - len(list_of_regs_to_upload) < 1:
                    region_is_the_only = 'yes'

            # Scenario: this setting WAS in place, and now we need to DELETE it
            if region_was_in_db == 'yes' and not region_is_the_only:
                for region in list_of_regs_to_upload:
                    cur.execute(
                        """DELETE FROM user_regional_preferences WHERE user_id=%s and forum_folder_num=%s;""",
                        (user_id, region),
                    )

            # Scenario: this setting WAS in place, but now it's the last one - we cannot delete it
            elif region_was_in_db == 'yes' and region_is_the_only:
                pass

            # Scenario: it's a NEW setting, we need to ADD it
            else:
                for region in list_of_regs_to_upload:
                    cur.execute(
                        """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values (%s, %s);""",
                        (user_id, region),
                    )

        except Exception as e:
            logging.info("failed to upload & download the list of user's regions")
            logging.exception(e)

    # Get the list of resulting regions
    cur.execute("""SELECT forum_folder_num from user_regional_preferences WHERE user_id=%s;""", (user_id,))

    user_curr_regs = cur.fetchall()
    user_curr_regs_list = [reg[0] for reg in user_curr_regs]

    for reg in user_curr_regs_list:
        if reg in rev_reg_dict:
            msg += ',\n &#8226; ' + rev_reg_dict[reg]

    msg = msg[1:]

    if is_first_entry:
        pre_msg = 'Бот может показывать поиски в любом регионе работы ЛА.\n'
        pre_msg += (
            'Вы можете подписаться на несколько регионов – просто кликните на соответствующие кнопки регионов.'
            '\nЧтобы ОТПИСАТЬСЯ от ненужных регионов – нажмите на соответствующую кнопку региона еще раз.\n\n'
        )
        pre_msg += 'Текущий список ваших регионов:'
        msg = pre_msg + msg
    elif region_is_the_only:
        msg = (
            'Ваш регион поисков настроен' + msg + '\n\nВы можете продолжить добавлять регионы, либо нажмите '
            'кнопку "в начало", чтобы продолжить работу с ботом.'
        )
    elif got_message in fed_okr_dict or got_message == b_fed_dist_pick_other:
        if user_curr_regs_list:
            msg = 'Текущий список ваших регионов:' + msg
        else:
            msg = 'Пока список выбранных регионов пуст. Выберите хотя бы один.'
    else:
        msg = (
            'Записали. Обновленный список ваших регионов:' + msg + '\n\nВы можете продолжить добавлять регионы, '
            'либо нажмите кнопку "в начало", чтобы '
            'продолжить работу с ботом.'
        )

    return msg


def get_last_bot_msg(cur: cursor, user_id: int) -> str:
    """Get the last bot message to user to define if user is expected to give exact answer"""

    cur.execute(
        """
        SELECT msg_type FROM msg_from_bot WHERE user_id=%s LIMIT 1;
        """,
        (user_id,),
    )

    extract = cur.fetchone()
    logging.info('get the last bot message to user to define if user is expected to give exact answer')
    logging.info(str(extract))

    if extract and extract != 'None':
        msg_type = extract[0]
    else:
        msg_type = None

    if msg_type:
        logging.info(f'before this message bot was waiting for {msg_type} from user {user_id}')
    else:
        logging.info(f'before this message bot was NOT waiting anything from user {user_id}')

    return msg_type


def generate_yandex_maps_place_link(lat: Union[float, str], lon: Union[float, str], param: str) -> str:
    """Compose a link to yandex map with the given coordinates"""

    coordinates_format = '{0:.5f}'

    if param == 'coords':
        display = str(coordinates_format.format(float(lat))) + ', ' + str(coordinates_format.format(float(lon)))
    else:
        display = 'Карта'

    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

    return msg


def save_user_pref_role(cur, user_id, role_desc):
    """save user role"""

    role_dict = {
        'я состою в ЛизаАлерт': 'member',
        'я хочу помогать ЛизаАлерт': 'new_member',
        'я ищу человека': 'relative',
        'у меня другая задача': 'other',
        'не хочу говорить': 'no_answer',
    }

    try:
        role = role_dict[role_desc]
    except:  # noqa
        role = 'unidentified'

    cur.execute("""UPDATE users SET role=%s where user_id=%s;""", (role, user_id))

    logging.info(f'[comm]: user {user_id} selected role {role}')

    return role


def check_if_user_has_no_regions(cur, user_id):
    """check if the user has at least one region"""

    cur.execute("""SELECT user_id FROM user_regional_preferences WHERE user_id=%s LIMIT 1;""", (user_id,))

    info_on_user_from_users = str(cur.fetchone())

    if info_on_user_from_users == 'None':
        no_regions = True
    else:
        no_regions = False

    return no_regions


def check_if_new_user(cur: cursor, user_id: int) -> bool:
    """check if the user is new or not"""

    cur.execute("""SELECT user_id FROM users WHERE user_id=%s LIMIT 1;""", (user_id,))

    info_on_user_from_users = str(cur.fetchone())

    if info_on_user_from_users == 'None':
        user_is_new = True
    else:
        user_is_new = False

    return user_is_new


def save_bot_reply_to_user(cur: cursor, user_id: int, bot_message: str) -> None:
    """save bot's reply to user in psql"""

    if len(bot_message) > 27 and bot_message[28] in {'Актуальные поиски за 60 дней', 'Последние 20 поисков в разде'}:
        bot_message = bot_message[28]

    cur.execute(
        """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
        (user_id, 'bot', datetime.datetime.now(), bot_message),
    )

    return None


def save_user_message_to_bot(cur: cursor, user_id: int, got_message: str) -> None:
    """save user's message to bot in psql"""

    cur.execute(
        """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
        (user_id, 'user', datetime.datetime.now(), got_message),
    )

    return None


def save_new_user(user_id: int, username: str) -> None:
    """send pubsub message to dedicated script to save new user"""

    username = username if username else 'unknown'
    message_for_pubsub = {
        'action': 'new',
        'info': {'user': user_id, 'username': username},
        'time': str(datetime.datetime.now()),
    }
    publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)

    return None


def check_onboarding_step(cur: cursor, user_id: int, user_is_new: bool) -> Tuple[int, str]:
    """checks the latest step of onboarding"""

    if user_is_new:
        return 0, 'start'

    try:
        cur.execute(
            """SELECT step_id, step_name, timestamp FROM user_onboarding 
                               WHERE user_id=%s ORDER BY step_id DESC;""",
            (user_id,),
        )
        raw_data = cur.fetchone()
        if raw_data:
            step_id, step_name, time = list(raw_data)
        else:
            step_id, step_name = 99, None

    except Exception as e:
        logging.exception(e)
        step_id, step_name = 99, None

    return step_id, step_name


def compose_msg_on_all_last_searches(cur: cursor, region: int) -> str:
    """Compose a part of message on the list of recent searches"""

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    text = ''

    # download the list from SEARCHES sql table
    cur.execute(
        """SELECT s2.* FROM 
            (SELECT search_forum_num, search_start_time, display_name, status, status, family_name, age 
            FROM searches 
            WHERE forum_folder_id=%s 
            ORDER BY search_start_time DESC 
            LIMIT 20) s2 
        LEFT JOIN search_health_check shc 
        ON s2.search_forum_num=shc.search_forum_num 
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""",
        (region,),
    )

    database = cur.fetchall()

    for line in database:
        search = SearchSummary()
        (
            search.topic_id,
            search.start_time,
            search.display_name,
            search.new_status,
            search.status,
            search.name,
            search.age,
        ) = list(line)

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age and search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        if not search.new_status:
            search.new_status = search.status

        if search.new_status in {'Ищем', 'Возобновлен'}:
            search.new_status = f'Ищем {time_counter_since_search_start(search.start_time)[0]}'

        text += f'{search.new_status} <a href="{pre_url}{search.topic_id}">{search.display_name}</a>\n'

    return text


def compose_user_preferences_message(cur: cursor, user_id: int) -> List[Union[List[str], str]]:
    """Compose a text for user on which types of notifications are enabled for zir"""

    cur.execute("""SELECT preference FROM user_preferences WHERE user_id=%s ORDER BY preference;""", (user_id,))
    user_prefs = cur.fetchall()

    prefs_wording = ''
    prefs_list = []
    if user_prefs and len(user_prefs) > 0:
        for user_pref_line in user_prefs:
            prefs_list.append(user_pref_line[0])
            if user_pref_line[0] == 'all':
                prefs_wording += 'все сообщения'
            elif user_pref_line[0] == 'new_searches':
                prefs_wording += ' &#8226; о новых поисках\n'
            elif user_pref_line[0] == 'status_changes':
                prefs_wording += ' &#8226; об изменении статуса\n'
            elif user_pref_line[0] == 'title_changes':
                prefs_wording += ' &#8226; об изменении заголовка\n'
            elif user_pref_line[0] == 'comments_changes':
                prefs_wording += ' &#8226; о всех комментариях\n'
            elif user_pref_line[0] == 'inforg_comments':
                prefs_wording += ' &#8226; о комментариях Инфорга\n'
            elif user_pref_line[0] == 'first_post_changes':
                prefs_wording += ' &#8226; об изменениях в первом посте\n'
            elif user_pref_line[0] == 'bot_news':
                pass
            else:
                prefs_wording += 'неизвестная настройка'
    else:
        prefs_wording += 'пока нет включенных уведомлений'

    prefs_wording_and_list = [prefs_wording, prefs_list]

    return prefs_wording_and_list


def save_user_pref_topic_type(cur, user_id, pref_id, user_role):
    def save(pref_type_id):
        cur.execute(
            """INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                                            values (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
            (user_id, pref_type_id, datetime.datetime.now()),
        )
        return None

    if not (cur and user_id and pref_id):
        return None

    if pref_id == 'default':
        if user_role in {'member', 'new_member'}:
            default_topic_type_id = [0, 3, 4, 5]  # 0=regular, 3=training, 4=info_support, 5=resonance
        else:
            default_topic_type_id = [0, 4, 5]  # 0=regular, 4=info_support, 5=resonance

        for type_id in default_topic_type_id:
            save(type_id)

    else:
        save(pref_id)

    return None


def record_topic_type(cur, user: int, type_id: int) -> None:
    """Insert a certain topic_type for a certain user_id into the DB"""

    cur.execute(
        """INSERT INTO user_pref_topic_type (user_id, topic_type_id, timestamp) 
                    VALUES (%s, %s, %s) ON CONFLICT (user_id, topic_type_id) DO NOTHING;""",
        (user, type_id, datetime.datetime.now()),
    )
    return None


def delete_topic_type(cur, user: int, type_id: int) -> None:
    """Delete a certain topic_type for a certain user_id from the DB"""

    cur.execute("""DELETE FROM user_pref_topic_type WHERE user_id=%s AND topic_type_id=%s;""", (user, type_id))
    return None


def check_saved_topic_types(cur, user: int) -> list:
    """check if user already has any preference"""

    saved_pref = []
    cur.execute("""SELECT topic_type_id FROM user_pref_topic_type WHERE user_id=%s ORDER BY 1;""", (user,))
    raw_data = cur.fetchall()
    if raw_data and str(raw_data) != 'None':
        for line in raw_data:
            saved_pref.append(line[0])

    logging.info(f'{saved_pref=}')

    return saved_pref


def set_search_follow_mode(cur: cursor, user_id: int, new_value: bool) -> None:
    filter_name_value = ['whitelist'] if new_value else ['']
    logging.info(f'{filter_name_value=}')
    cur.execute(
        """INSERT INTO user_pref_search_filtering (user_id, filter_name) values (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET filter_name=%s;""",
        (user_id, filter_name_value, filter_name_value),
    )
    return None


def get_search_follow_mode(cur, user_id: int):
    cur.execute("""SELECT filter_name FROM user_pref_search_filtering WHERE user_id=%s LIMIT 1;""", (user_id,))
    result_fetched = cur.fetchone()
    result = result_fetched and 'whitelist' in result_fetched[0]
    return result


def delete_last_user_inline_dialogue(cur, user_id: int) -> None:
    """Delete form DB the user's last interaction via inline buttons"""

    cur.execute("""DELETE FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))
    return None


def get_last_user_inline_dialogue(cur, user_id: int) -> list:
    """Get from DB the user's last interaction via inline buttons"""

    cur.execute("""SELECT message_id FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))
    message_id_lines = cur.fetchall()

    message_id_list = []
    if message_id_lines and len(message_id_lines) > 0:
        for message_id_line in message_id_lines:
            message_id_list.append(message_id_line[0])

    return message_id_list


def save_last_user_inline_dialogue(cur, user_id: int, message_id: int) -> None:
    """Save to DB the user's last interaction via inline buttons"""

    cur.execute(
        """INSERT INTO communications_last_inline_msg 
                    (user_id, timestamp, message_id) values (%s, CURRENT_TIMESTAMP AT TIME ZONE 'UTC', %s)
                    ON CONFLICT (user_id, message_id) DO 
                    UPDATE SET timestamp=CURRENT_TIMESTAMP AT TIME ZONE 'UTC';""",
        (user_id, message_id),
    )
    return None


def compose_msg_on_user_setting_fullness(cur, user_id: int) -> Union[str, None]:
    """Create a text of message, which describes the degree on how complete user's profile is.
    More settings set – more complete profile it. It's done to motivate users to set the most tailored settings."""

    if not cur or not user_id:
        return None

    try:
        cur.execute(
            """SELECT
                            user_id 
                            , CASE WHEN role IS NOT NULL THEN TRUE ELSE FALSE END as role 
                            , CASE WHEN (SELECT TRUE FROM user_pref_age WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS age
                            , CASE WHEN (SELECT TRUE FROM user_coordinates WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS coords    
                            , CASE WHEN (SELECT TRUE FROM user_pref_radius WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS radius
                            , CASE WHEN (SELECT TRUE FROM user_pref_region WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS region
                            , CASE WHEN (SELECT TRUE FROM user_pref_topic_type WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS topic_type
                            , CASE WHEN (SELECT TRUE FROM user_pref_urgency WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS urgency
                            , CASE WHEN (SELECT TRUE FROM user_preferences WHERE user_id=%s 
                                AND preference!='bot_news' LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS notif_type
                            , CASE WHEN (SELECT TRUE FROM user_regional_preferences WHERE user_id=%s LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS region_old
                            , CASE WHEN (SELECT TRUE FROM user_forum_attributes WHERE user_id=%s
                                AND status = 'verified' LIMIT 1) 
                                THEN TRUE ELSE FALSE END AS forum
                        FROM users WHERE user_id=%s;
                        """,
            (
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
                user_id,
            ),
        )

        raw_data = cur.fetchone()

        if not raw_data:
            return None

        (
            _,
            pref_role,
            pref_age,
            pref_coords,
            pref_radius,
            pref_region,
            pref_topic_type,
            pref_urgency,
            pref_notif_type,
            pref_region_old,
            pref_forum,
        ) = raw_data

        list_of_settings = [pref_notif_type, pref_region_old, pref_coords, pref_radius, pref_age, pref_forum]
        user_score = int(round(sum(list_of_settings) / len(list_of_settings) * 100, 0))

        logging.info(f'List of user settings activation: {list_of_settings=}')
        logging.info(f'User settings completeness score is {user_score}')

        if user_score == 100:
            return None

        user_score_emoji = (
            f'{user_score // 10}\U0000fe0f\U000020e3{user_score - (user_score // 10) * 10}\U0000fe0f\U000020e3'
        )
        message_text = (
            f'Вы настроили бот на {user_score_emoji}%.\n\nЧтобы сделать бот максимально эффективным '
            f'именно для вас, рекомендуем настроить следующие параметры:\n'
        )
        if not pref_notif_type:
            message_text += ' - Тип уведомлений,\n'
        if not pref_region_old:
            message_text += ' - Регион,\n'
        if not pref_coords:
            message_text += ' - Домашние координаты,\n'
        if not pref_radius:
            message_text += ' - Максимальный радиус,\n'
        if not pref_age:
            message_text += ' - Возрастные группы БВП,\n'
        if not pref_forum:
            message_text += ' - Связать бот с форумом ЛА,\n'
        message_text = message_text[:-2]

        return message_text

    except Exception as e:
        logging.info('Exception in "compose_msg_on_user_setting_fullness" function')
        logging.exception(e)
        return None
