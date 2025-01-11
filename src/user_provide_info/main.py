"""Function acts as API for Searches Map WebApp made as a part of Searcher Bot
The current script checks Telegram authentication and retrieves user's key data and list of searches"""

# TODO - add functions descriptions
# TODO – add functions typing hints

import datetime
import hashlib
import hmac
import json
import logging
import re
import urllib.request
from urllib.parse import unquote

import functions_framework
import google.cloud.logging
import psycopg2
from bs4 import BeautifulSoup
from google.cloud import secretmanager

url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
req = urllib.request.Request(url)
req.add_header('Metadata-Flavor', 'Google')
project_id = urllib.request.urlopen(req).read().decode()
client = secretmanager.SecretManagerServiceClient()

log_client = google.cloud.logging.Client()
log_client.setup_logging()


def get_secrets(secret_request):
    """Get GCP secret"""

    name = f'projects/{project_id}/secrets/{secret_request}/versions/latest'
    response = client.access_secret_version(name=name)

    return response.payload.data.decode('UTF-8')


def sql_connect_by_psycopg2():
    """connect to GCP SLQ via PsycoPG2"""

    db_user = get_secrets('cloud-postgres-username')
    db_pass = get_secrets('cloud-postgres-password')
    db_name = get_secrets('cloud-postgres-db-name')
    db_conn = get_secrets('cloud-postgres-connection-name')
    db_host = '/cloudsql/' + db_conn

    conn_psy = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_pass)
    conn_psy.autocommit = True

    return conn_psy


def verify_telegram_data_json(user_input, token):
    """verify the received dict is issued by telegram, which means user is authenticated with telegram"""

    if not user_input or not isinstance(user_input, dict) or 'hash' not in user_input.keys() or not token:
        return False

    hash_from_telegram = user_input['hash']
    sorted_dict = {key: value for key, value in sorted(user_input.items())}

    data_array = []
    for key, value in sorted_dict.items():
        if key != 'hash':
            data_array.append(f'{key}={value}')
    data_check_string = '\n'.join(data_array)

    # Convert bot_token to bytes and compute its SHA256 hash
    secret_key = hashlib.sha256(token.encode()).digest()

    # Compute the HMAC-SHA-256 signature of the data_check_string
    hmac_signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    # Compare the computed signature with the received hash
    if hmac_signature == hash_from_telegram:
        # Data is from Telegram
        return True
    else:
        # Data is not from Telegram
        return False


def verify_telegram_data_string(user_input, token):
    """verify the received dict is issued by telegram, which means user is authenticated with telegram"""

    data_check_string = unquote(user_input)

    data_check_arr = data_check_string.split('&')
    needle = 'hash='
    hash_item = ''
    telegram_hash = ''
    for item in data_check_arr:
        if item[0 : len(needle)] == needle:
            telegram_hash = item[len(needle) :]
            hash_item = item
    data_check_arr.remove(hash_item)
    data_check_arr.sort()
    data_check_string = '\n'.join(data_check_arr)
    secret_key = hmac.new('WebAppData'.encode(), token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if calculated_hash == telegram_hash:
        return True
    else:
        return False


def verify_telegram_data(user_input, token):
    """verify if u"""
    if isinstance(user_input, str):
        result = verify_telegram_data_string(user_input, token)
    else:
        result = verify_telegram_data_json(user_input, token)

    return result


def evaluate_city_locations(city_locations):
    if not city_locations:
        logging.info('no city_locations')
        return None

    cl_eval = eval(city_locations)
    if not cl_eval:
        logging.info('no eval of city_locations')
        return None

    if not isinstance(cl_eval, list):
        logging.info('eval of city_locations is not list')
        return None

    first_coords = cl_eval[0]

    if not first_coords:
        logging.info('no first coords in city_locations')
        return None

    if not isinstance(first_coords, list):
        logging.info('fist coords in city_locations is not list')
        return None

    logging.info(f'city_locations has coords {first_coords}')

    return [first_coords]


def time_counter_since_search_start(start_time):
    """Count timedelta since the beginning of search till now, return phrase in Russian and diff in days"""

    start_diff = datetime.timedelta(hours=0)

    now = datetime.datetime.now()
    diff = now - start_time - start_diff

    first_word_parameter = ''

    # <20 minutes -> "Начинаем искать"
    if (diff.total_seconds() / 60) < 20:
        phrase = 'Начинаем искать'

    # 20 min - 1 hour -> "Ищем ХХ минут"
    elif (diff.total_seconds() / 3600) < 1:
        phrase = first_word_parameter + str(round(int(diff.total_seconds() / 60), -1)) + ' минут'

    # 1-24 hours -> "Ищем ХХ часов"
    elif diff.days < 1:
        phrase = first_word_parameter + str(int(diff.total_seconds() / 3600))
        if int(diff.total_seconds() / 3600) in {1, 21}:
            phrase += ' час'
        elif int(diff.total_seconds() / 3600) in {2, 3, 4, 22, 23}:
            phrase += ' часа'
        else:
            phrase += ' часов'

    # >24 hours -> "Ищем Х дней"
    else:
        phrase = first_word_parameter + str(diff.days)
        if str(int(diff.days))[-1] == '1' and (int(diff.days)) != 11:
            phrase += ' день'
        elif int(diff.days) in {12, 13, 14}:
            phrase += ' дней'
        elif str(int(diff.days))[-1] in {'2', '3', '4'}:
            phrase += ' дня'
        else:
            phrase += ' дней'

    return [phrase, diff.days]


def get_user_data_from_db(user_id: int) -> dict:
    """if user_is is a current bot's user – than retrieves user's data like home coords, radius, list of searches
    if user_id is not a user of bot – than retrieves a "demo" data with fake home coords, radius and real list of
    searches for Moscow Region"""

    conn_psy = sql_connect_by_psycopg2()
    cur = conn_psy.cursor()

    # create user basic parameters
    cur.execute(
        """SELECT u.user_id, uc.latitude, uc.longitude, ur.radius
                    FROM users AS u
                    LEFT JOIN user_coordinates AS uc
                    ON u.user_id=uc.user_id
                    LEFT JOIN user_pref_radius AS ur
                    ON uc.user_id=ur.user_id
                    WHERE u.user_id=%s;""",
        (user_id,),
    )
    raw_data = cur.fetchone()

    if not raw_data:
        user_params = {'curr_user': False}
        user_params['home_lat'] = 55.752702  # Kremlin
        user_params['home_lon'] = 37.622914  # Kremlin
        user_params['radius'] = 100  # demo radius = 100 km
        user_params['regions'] = [28, 29]  # Moscow + Moscow Region

        # create searches list – FOR DEMO ONLY Moscow Region (folders 276 and 41)
        cur.execute(
            """WITH
            user_regions AS (
                SELECT forum_folder_num from user_regional_preferences
                WHERE forum_folder_num=276 OR forum_folder_num=41),
            user_regions_filtered AS (
                SELECT ur.*
                FROM user_regions AS ur
                LEFT JOIN geo_folders AS f
                ON ur.forum_folder_num=f.folder_id
                WHERE f.folder_type='searches'),
            s2 AS (SELECT search_forum_num, search_start_time, display_name, status, family_name,
                topic_type, topic_type_id, city_locations, age_min, age_max
                FROM searches
                WHERE forum_folder_id IN (SELECT forum_folder_num FROM user_regions_filtered)
                AND status != 'НЖ'
                AND status != 'НП'
                AND status != 'Завершен'
                AND status != 'Найден'
                AND topic_type_id != 1
                ORDER BY search_start_time DESC
                LIMIT 30),
            s3 AS (SELECT s2.*
                FROM s2
                LEFT JOIN search_health_check shc
                ON s2.search_forum_num=shc.search_forum_num
                WHERE (shc.status is NULL OR shc.status='ok' OR shc.status='regular')
                ORDER BY s2.search_start_time DESC),
            s4 AS (SELECT s3.*, sfp.content
                FROM s3
                LEFT JOIN search_first_posts AS sfp
                ON s3.search_forum_num=sfp.search_id
                WHERE sfp.actual = True),
            s5 AS (SELECT s4.*, sc.latitude, sc.longitude, sc.coord_type
                FROM s4
                LEFT JOIN search_coordinates AS sc
                ON s4.search_forum_num=sc.search_id)

            SELECT distinct s5.*, max(parsed_time) OVER (PARTITION BY cl.search_forum_num) AS last_change_time
                FROM s5
                LEFT JOIN change_log AS cl
                ON s5.search_forum_num=cl.search_forum_num
                ;""",
            (user_id,),
        )

    else:
        user_params = {'curr_user': True}
        (
            user_params['user_id'],
            user_params['home_lat'],
            user_params['home_lon'],
            user_params['radius'],
        ) = raw_data
        if user_params['home_lat']:
            user_params['home_lat'] = float(user_params['home_lat'])
        if user_params['home_lon']:
            user_params['home_lon'] = float(user_params['home_lon'])

        # create folders (regions) list
        cur.execute(
            """WITH
                        step_0 AS (
                            SELECT
                                urp.forum_folder_num,
                                f.division_id AS region_id,
                                r.polygon_id
                            FROM user_regional_preferences AS urp
                            LEFT JOIN geo_folders AS f
                            ON urp.forum_folder_num=f.folder_id
                            JOIN geo_regions AS r
                            ON f.division_id=r.division_id
                            WHERE urp.user_id=%s
                        )
                        SELECT distinct polygon_id
                        FROM step_0
                        ORDER BY 1;""",
            (user_id,),
        )

        raw_data = cur.fetchall()
        if not raw_data:
            user_params['regions'] = []
        else:
            user_regions = []
            for line in raw_data:
                user_regions.append(line[0])
            user_params['regions'] = user_regions

        # create searches list
        cur.execute(
            """WITH
            user_regions AS (
                select forum_folder_num from user_regional_preferences where user_id=%s),
            user_regions_filtered AS (
                SELECT ur.*
                FROM user_regions AS ur
                LEFT JOIN geo_folders AS f
                ON ur.forum_folder_num=f.folder_id
                WHERE f.folder_type='searches'),
            s2 AS (SELECT search_forum_num, search_start_time, display_name, status, family_name,
                topic_type, topic_type_id, city_locations, age_min, age_max
                FROM searches
                WHERE forum_folder_id IN (SELECT forum_folder_num FROM user_regions_filtered)
                AND status != 'НЖ'
                AND status != 'НП'
                AND status != 'Завершен'
                AND status != 'Найден'
                AND topic_type_id != 1
                ORDER BY search_start_time DESC
                LIMIT 30),
            s3 AS (SELECT s2.*
                FROM s2
                LEFT JOIN search_health_check shc
                ON s2.search_forum_num=shc.search_forum_num
                WHERE (shc.status is NULL OR shc.status='ok' OR shc.status='regular')
                ORDER BY s2.search_start_time DESC),
            s4 AS (SELECT s3.*, sfp.content
                FROM s3
                LEFT JOIN search_first_posts AS sfp
                ON s3.search_forum_num=sfp.search_id
                WHERE sfp.actual = True),
            s5 AS (SELECT s4.*, sc.latitude, sc.longitude, sc.coord_type
                FROM s4
                LEFT JOIN search_coordinates AS sc
                ON s4.search_forum_num=sc.search_id)

            SELECT distinct s5.*, max(parsed_time) OVER (PARTITION BY cl.search_forum_num) AS last_change_time
                FROM s5
                LEFT JOIN change_log AS cl
                ON s5.search_forum_num=cl.search_forum_num
                ;""",
            (user_id,),
        )

    raw_data = cur.fetchall()

    if not raw_data:
        user_params['searches'] = []
    else:
        user_searches = []
        for line in raw_data:
            (
                search_id,
                search_start_time,
                display_name,
                status,
                family_name,
                topic_type,
                topic_type_id,
                city_locations,
                age_min,
                age_max,
                first_post,
                lat,
                lon,
                coord_type,
                last_change_time,
            ) = line

            # define "freshness" of the search
            creation_freshness, creation_freshness_days = time_counter_since_search_start(search_start_time)
            update_freshness, update_freshness_days = time_counter_since_search_start(last_change_time)
            logging.info(f'{search_id=}')
            logging.info(f'{creation_freshness_days=}')
            logging.info(f'{update_freshness_days=}')
            logging.info(f'{min(creation_freshness_days, update_freshness_days)=}')
            search_is_old = False
            if creation_freshness_days > 3 and update_freshness_days > 3:
                search_is_old = True

            # define "exact_coords" – an variable showing if coordinates are explicityply provided ("exact")
            # or geocoded (not "exact")
            if not coord_type:
                exact_coords = False
            elif coord_type not in {'1. coordinates w/ word coord', '2. coordinates w/o word coord'}:
                exact_coords = False
            else:
                exact_coords = True

            # define "coords"
            if exact_coords:
                coords = [[eval(lat), eval(lon)]]
            else:
                coords = evaluate_city_locations(city_locations)

                if not coords and lat and lon:
                    coords = [[eval(lat), eval(lon)]]
                elif not coords:
                    coords = [[]]

            # define "link"
            link = f'https://lizaalert.org/forum/viewtopic.php?t={search_id}'

            # define "content"
            content = clean_up_content(first_post)

            # define "search_type"
            if topic_type_id == 0:
                search_type = 'Обычный поиск'
            else:
                search_type = 'Особый поиск'  # TODO – to be decomposed in greater details

            user_search = {
                'name': search_id,
                'coords': coords,
                'exact_coords': exact_coords,
                'content': content,
                'display_name': display_name,
                'freshness': creation_freshness,
                'link': link,
                'search_status': status,
                'search_type': search_type,
                'search_is_old': search_is_old,
            }

            if coords[0]:
                user_searches.append(user_search)
        user_params['searches'] = user_searches

    cur.close()
    conn_psy.close()

    return user_params


def save_user_statistics_to_db(user_id: int, response: bool) -> None:
    """save user's interaction into DB"""

    json_to_save = json.dumps({'ok': response})

    conn_psy = sql_connect_by_psycopg2()
    cur = conn_psy.cursor()

    try:
        cur.execute(
            """INSERT INTO stat_map_usage
                        (user_id, timestamp, response)
                        VALUES (%s, CURRENT_TIMESTAMP, %s);""",
            (user_id, json_to_save),
        )
    except Exception as e:
        logging.exception(e)

    cur.close()
    conn_psy.close()

    return None


def clean_up_content(init_content):
    def cook_soup(content):
        content = BeautifulSoup(content, 'lxml')

        return content

    def prettify_soup(content):
        for s in content.find_all('strong', {'class': 'text-strong'}):
            s.unwrap()

        for s in content.find_all('span'):
            try:
                if s.attrs['style'] and s['style'] and len(s['style']) > 5 and s['style'][0:5] == 'color':
                    s.unwrap()
            except Exception as e:
                logging.exception(e)
                continue

        deleted_text = content.find_all('span', {'style': 'text-decoration:line-through'})
        for case in deleted_text:
            case.decompose()

        for dd in content.find_all('dd', style='display:none'):
            del dd['style']

        return content

    def remove_links(content):
        for tag in content.find_all('a'):
            if tag.name == 'a' and not re.search(r'\[[+−]]', tag.text):
                tag.unwrap()

        return content

    def remove_irrelevant_content(content):
        # language=regexp
        patterns = (
            r'(?i)(Карты.*\n|'
            r'Ориентировка на печать.*\n|'
            r'Ориентировка на репост.*\n|'
            r'\[\+] СМИ.*\n|'
            r'СМИ\s.*\n|'
            r'Задача на поиске с которой может помочь каждый.*\n|'
            r'ВНИМАНИЕ! Всем выезжающим иметь СИЗ.*\n|'
            r'С признаками ОРВИ оставайтесь дома.*\n|'
            r'Берегите себя и своих близких!.*\n|'
            r'Если же представитель СМИ хочет.*\n|'
            r'8\(800\)700-54-52 или.*\n|'
            r'Предоставлять комментарии по поиску.*\n|'
            r'Таблица прозвона больниц.*\n|'
            r'Запрос на согласование фото.*(\n|(\s*)?$)|'
            r'Все фото.*(\n|(\s*)?$)|'
            r'Написать инфоргу.*в (Telegram|Телеграмм?)(\n|(\s*)?$)|'
            r'Горячая линия отряда:.*(\n|(\s*)?$))'
        )

        content = re.sub(patterns, '', content)
        content = re.sub(r'[\s_-]*$', '', content)
        content = re.sub(r'\n\n', r'\n', content)
        content = re.sub(r'\n\n', r'\n', content)

        return content

    def make_html(content):
        content = re.sub(r'\n', '<br>', content)

        return content

    if not init_content or re.search(r'Для просмотра этого форума вы должны быть авторизованы', init_content):
        return None

    reco_content = cook_soup(init_content)
    reco_content = prettify_soup(reco_content)
    reco_content = remove_links(reco_content)
    reco_content = reco_content.text
    reco_content = remove_irrelevant_content(reco_content)
    reco_content = make_html(reco_content)
    logging.info(f'{reco_content=}')

    return reco_content


@functions_framework.http
def main(request):
    # For more information about CORS and CORS preflight requests, see:
    # https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request
    allowed_origins = ['https://web_app.storage.googleapis.com', 'https://storage.googleapis.com']
    origin = None
    try:
        origin = request.headers.get('Origin')
        logging.info(f'{origin=}')

    except Exception as e:
        logging.exception(e)

    origin_to_show = allowed_origins[1]
    if origin in allowed_origins:
        origin_to_show = origin
    logging.info(f'{origin_to_show=}')

    # Set CORS headers for the preflight request
    if request.method == 'OPTIONS':
        # Allows GET requests from any origin with the Content-Type
        # header and caches preflight response for an 3600s
        headers = {
            'Access-Control-Allow-Origin': origin_to_show,
            'Access-Control-Allow-Methods': ['GET', 'POST', 'OPTIONS'],
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600',
        }  # https://storage.googleapis.com

        logging.info(f'{headers=}')

        return ('', 204, headers)

    # Set CORS headers for the main request
    headers = {'Access-Control-Allow-Origin': origin_to_show}
    logging.info(f'{headers=}')

    logging.info(request)
    request_json = request.get_json(silent=True)
    logging.info(request_json)
    request_args = request.args
    response = {'ok': False}
    reason = None

    if not request_json:
        reason = 'No json/string received'
        logging.info(request_args)

    bot_token = get_secrets('bot_api_token__prod')
    process_the_data = verify_telegram_data(request_json, bot_token)

    if not process_the_data:
        reason = 'Provided json is not validated'
        logging.info(f'the incoming json is {request_json}')

    elif not isinstance(request_json, str) and 'id' not in request_json:
        reason = 'No user_id in json provided'
        logging.info(f'the incoming json is {request_json}')

    elif not isinstance(request_json, str) and 'id' in request_json and not isinstance(request_json['id'], int):
        reason = 'user_id is not a digit'
        logging.info(f'the incoming json is {request_json}')

    if reason:
        logging.info(f'{reason=}')
        response['reason'] = reason
        # MEMO - below we use "0" only to track number of unsuccessful api calls
        save_user_statistics_to_db(0, False)
        return response, 200, headers

    if not isinstance(request_json, str):
        user_id = request_json['id']
    else:
        user_item = unquote(request_json)
        user_id = int(re.findall(r'(?<="id":)\d{3,20}', user_item)[0])
    logging.info(f'YES, {user_id=} is received!')
    logging.info(f'the incoming json is {request_json}')
    params = get_user_data_from_db(user_id)

    response = {'ok': True, 'user_id': user_id, 'params': params}

    logging.info(f'the RESULT {response}')

    save_user_statistics_to_db(user_id, True)

    return (json.dumps(response), 200, headers)
