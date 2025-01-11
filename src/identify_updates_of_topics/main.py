"""Script takes as input the list of recently-updated forum folders. Then it parses first 20 searches (aka topics)
and saves into PSQL if there are any updates"""

import ast
import base64
import copy
import json
import logging
import random
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import google.auth.transport.requests
import google.cloud.logging
import google.oauth2.id_token
import requests
import sqlalchemy
from bs4 import BeautifulSoup, SoupStrainer  # noqa
from geopy.geocoders import Nominatim
from google.cloud import pubsub_v1, secretmanager, storage
from yandex_geocoder import Client, exceptions

url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
req = urllib.request.Request(url)
req.add_header('Metadata-Flavor', 'Google')
project_id = urllib.request.urlopen(req).read().decode()

client = secretmanager.SecretManagerServiceClient()

publisher = pubsub_v1.PublisherClient()

log_client = google.cloud.logging.Client()
log_client.setup_logging()

# Sessions – to reuse for reoccurring requests
requests_session = None

# to be reused by different functions
block_of_profile_rough_code = None

dict_status_words = {
    'жив': 'one',
    'жива': 'one',
    'живы': 'many',
    'завершен': 'na',
    'завершён': 'na',
    'идет': 'na',
    'идёт': 'na',
    'информации': 'na',
    'найден': 'one',
    'найдена': 'one',
    'найдены': 'many',
    'погиб': 'one',
    'погибла': 'one',
    'погибли': 'many',
    'поиск': 'na',
    'приостановлен': 'na',
    'проверка': 'na',
    'похищен': 'one',
    'похищена': 'one',
    'похищены': 'many',
    'пропал': 'one',
    'пропала': 'one',
    'пропали': 'many',
    'остановлен': 'na',
    'стоп': 'na',
    'эвакуация': 'na',
}
dict_ignore = {'', ':'}


class SearchSummary:
    def __init__(
        self,
        topic_type=None,
        topic_type_id=None,
        topic_id=None,
        parsed_time=None,
        status=None,
        title=None,
        link=None,
        start_time=None,
        num_of_replies=None,
        name=None,
        display_name=None,
        age=None,
        searches_table_id=None,
        folder_id=None,
        age_max=None,
        age_min=None,
        num_of_persons=None,
        locations=None,
        new_status=None,
        full_dict=None,
    ):
        self.topic_type = topic_type
        self.topic_type_id = topic_type_id
        self.topic_id = topic_id
        self.parsed_time = parsed_time
        self.status = status
        self.title = title
        self.link = link
        self.start_time = start_time
        self.num_of_replies = num_of_replies
        self.name = name
        self.display_name = display_name
        self.age = age
        self.id = searches_table_id
        self.folder_id = folder_id
        self.age_max = age_max
        self.age_min = age_min
        self.num_of_persons = num_of_persons
        self.locations = locations
        self.new_status = new_status
        self.full_dict = full_dict

    def __str__(self):
        return (
            f'{self.parsed_time} – {self.folder_id} / {self.topic_id} : {self.name} - {self.age} – '
            f'{self.num_of_replies}. NEW: {self.display_name} – {self.age_min} – {self.age_max} – '
            f'{self.num_of_persons}'
        )


def set_cloud_storage(bucket_name, folder_num):
    """sets the basic parameters for connection to txt file in cloud storage, which stores searches snapshots"""

    if isinstance(folder_num, int) or folder_num == 'geocode':
        blob_name = str(folder_num) + '.txt'
    else:
        blob_name = folder_num
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)

    return blob


def write_snapshot_to_cloud_storage(bucket_to_write, what_to_write, folder_num):
    """writes current search's snapshot to txt file in cloud storage"""

    blob = set_cloud_storage(bucket_to_write, folder_num)
    blob.upload_from_string(what_to_write)

    return None


def read_snapshot_from_cloud_storage(bucket_to_read, folder_num):
    """reads previous search's snapshot from txt file in cloud storage"""

    try:
        blob = set_cloud_storage(bucket_to_read, folder_num)
        contents_as_bytes = blob.download_as_string()
        contents = str(contents_as_bytes, 'utf-8')
    except:  # noqa
        contents = None

    return contents


def read_yaml_from_cloud_storage(bucket_to_read, folder_num):
    """reads yaml in cloud storage"""

    try:
        blob = set_cloud_storage(bucket_to_read, folder_num)
        contents_as_bytes = blob.download_as_string()
        contents = contents_as_bytes
    except:  # noqa
        contents = None

    return contents


def save_last_api_call_time_to_psql(db: sqlalchemy.engine, geocoder: str) -> bool:
    """Used to track time of the last api call to geocoders. Saves the current timestamp in UTC in psql"""

    conn = None
    try:
        conn = db.connect()
        stmt = sqlalchemy.text(
            """UPDATE geocode_last_api_call SET timestamp=:a AT TIME ZONE 'UTC' WHERE geocoder=:b;"""
        )
        conn.execute(stmt, a=datetime.now(timezone.utc), b=geocoder)
        conn.close()

        return True

    except Exception as e:
        logging.info(f'UNSUCCESSFUL saving last api call time to geocoder {geocoder}')
        logging.exception(e)
        notify_admin(f'UNSUCCESSFUL saving last api call time to geocoder {geocoder}')
        if conn:
            conn.close()

        return False


def get_last_api_call_time_from_psql(db: sqlalchemy.engine, geocoder: str) -> datetime.timestamp:
    """Used to track time of the last api call to geocoders. Gets the last timestamp in UTC saved in psql"""

    conn = None
    last_call = None
    try:
        conn = db.connect()
        stmt = sqlalchemy.text("""SELECT timestamp FROM geocode_last_api_call WHERE geocoder=:a LIMIT 1;""")
        last_call = conn.execute(stmt, a=geocoder).fetchone()
        last_call = last_call[0]
        conn.close()

    except Exception as e:
        logging.info(f'UNSUCCESSFUL getting last api call time of geocoder {geocoder}')
        logging.exception(e)
        notify_admin(f'UNSUCCESSFUL getting last api call time of geocoder {geocoder}')
        if conn:
            conn.close()

    return last_call


def rate_limit_for_api(db: sqlalchemy.engine, geocoder: str) -> None:
    """sleeps certain time if api calls are too frequent"""

    # check that next request won't be in less a SECOND from previous
    prev_api_call_time = get_last_api_call_time_from_psql(db=db, geocoder=geocoder)

    if not prev_api_call_time:
        return None

    if geocoder == 'yandex':
        return None

    now_utc = datetime.now(timezone.utc)
    time_delta_bw_now_and_next_request = prev_api_call_time - now_utc + timedelta(seconds=1)

    logging.info(f'{prev_api_call_time=}')
    logging.info(f'{now_utc=}')
    logging.info(f'{time_delta_bw_now_and_next_request=}')

    if time_delta_bw_now_and_next_request.total_seconds() > 0:
        time.sleep(time_delta_bw_now_and_next_request.total_seconds())
        logging.info(f'rate limit for {geocoder}: sleep {time_delta_bw_now_and_next_request.total_seconds()}')
        notify_admin(f'rate limit for {geocoder}: sleep {time_delta_bw_now_and_next_request.total_seconds()}')

    return None


def get_coordinates(db, address):
    """convert address string into a pair of coordinates"""

    def get_geolocation_form_psql(db2, address_string):
        """get results of geocoding from psql"""

        with db2.connect() as conn:
            stmt = sqlalchemy.text(
                """SELECT address, status, latitude, longitude, geocoder from geocoding WHERE address=:a
                ORDER BY id DESC LIMIT 1; """
            )
            saved_result = conn.execute(stmt, a=address_string).fetchone()
            conn.close()

        logging.info(f'{address_string=}')
        logging.info(f'{saved_result=}')

        # there is a psql record on this address - no geocoding activities are required
        if saved_result:
            if saved_result[1] == 'ok':
                latitude = saved_result[2]
                longitude = saved_result[3]
                geocoder = saved_result[4]
                return 'ok', latitude, longitude, geocoder

            elif saved_result[1] == 'fail':
                return 'fail', None, None, None

        return None, None, None, None

    def save_geolocation_in_psql(db2, address_string, status, latitude, longitude, geocoder):
        """save results of geocoding to avoid multiple requests to openstreetmap service"""
        """the Geocoder HTTP API may not exceed 1000 per day"""

        try:
            with db2.connect() as conn:
                stmt = sqlalchemy.text(
                    """INSERT INTO geocoding (address, status, latitude, longitude, geocoder, timestamp) VALUES
                    (:a, :b, :c, :d, :e, :f)
                    ON CONFLICT(address) DO
                    UPDATE SET status=EXCLUDED.status, latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                    geocoder=EXCLUDED.geocoder, timestamp=EXCLUDED.timestamp;"""
                )
                conn.execute(
                    stmt, a=address_string, b=status, c=latitude, d=longitude, e=geocoder, f=datetime.now(timezone.utc)
                )
                conn.close()

        except Exception as e2:
            logging.info(f'ERROR: saving geolocation to psql failed: {address_string}, {status}')
            logging.exception(e2)
            notify_admin(f'ERROR: saving geolocation to psql failed: {address_string}, {status}')

        return None

    def get_coordinates_from_address_by_osm(address_string):
        """return coordinates on the request of address string"""
        """NB! openstreetmap requirements: NO more than 1 request per 1 second, no doubling requests"""
        """MEMO: documentation on API: https://operations.osmfoundation.org/policies/nominatim/"""

        latitude = None
        longitude = None
        osm_identifier = get_secrets('osm_identifier')
        geolocator = Nominatim(user_agent=osm_identifier)

        try:
            search_location = geolocator.geocode(address_string, timeout=10000)
            logging.info(f'geo_location by osm: {search_location}')
            if search_location:
                latitude, longitude = search_location.latitude, search_location.longitude

        except Exception as e6:
            logging.info(f'Error in func get_coordinates_from_address_by_osm for address: {address_string}. Repr: ')
            logging.exception(e6)
            notify_admin('ERROR: get_coords_from_address failed.')

        return latitude, longitude

    def get_coordinates_from_address_by_yandex(address_string: str) -> (float, float):
        """return coordinates on the request of address string, geocoded by yandex"""

        latitude = None
        longitude = None
        yandex_api_key = get_secrets('yandex_api_key')
        yandex_client = Client(yandex_api_key)

        try:
            coordinates = yandex_client.coordinates(address_string)
            logging.info(f'geo_location by yandex: {coordinates}')
        except Exception as e2:
            coordinates = None
            if isinstance(e2, exceptions.NothingFound):
                logging.info(f'address "{address_string}" not found by yandex')
            elif (
                isinstance(e2, exceptions.YandexGeocoderException)
                or isinstance(e2, exceptions.UnexpectedResponse)
                or isinstance(e2, exceptions.InvalidKey)
            ):
                logging.info('unexpected yandex error')
            else:
                logging.info('unexpected error:')
                logging.exception(e2)

        if coordinates:
            longitude, latitude = float(coordinates[0]), float(coordinates[1])

        return latitude, longitude

    try:
        # check if this address was already geolocated and saved to psql
        saved_status, lat, lon, saved_geocoder = get_geolocation_form_psql(db, address)

        if lat and lon:
            return lat, lon

        elif saved_status == 'fail' and saved_geocoder == 'yandex':
            return None, None

        elif not saved_status:
            # when there's no saved record
            rate_limit_for_api(db=db, geocoder='osm')
            lat, lon = get_coordinates_from_address_by_osm(address)
            api_call_time_saved = save_last_api_call_time_to_psql(db=db, geocoder='osm')
            logging.info(f'{api_call_time_saved=}')

            if lat and lon:
                saved_status = 'ok'
                save_geolocation_in_psql(db, address, saved_status, lat, lon, 'osm')
            else:
                saved_status = 'fail'

        if saved_status == 'fail' and (saved_geocoder == 'osm' or not saved_geocoder):
            # then we need to geocode with yandex
            rate_limit_for_api(db=db, geocoder='yandex')
            lat, lon = get_coordinates_from_address_by_yandex(address)
            api_call_time_saved = save_last_api_call_time_to_psql(db=db, geocoder='yandex')
            logging.info(f'{api_call_time_saved=}')

            if lat and lon:
                saved_status = 'ok'
            else:
                saved_status = 'fail'
            save_geolocation_in_psql(db, address, saved_status, lat, lon, 'yandex')

        return lat, lon

    except Exception as e:
        logging.info('TEMP - LOC - New getting coordinates from title failed')
        logging.exception(e)
        notify_admin('ERROR: major geocoding script failed')

    return None, None


def parse_coordinates(db, search_num):
    """finds coordinates of the search"""

    global requests_session

    def parse_address_from_title(initial_title):
        after_age = 0
        age_dict = [' год ', ' год', ' года ', ' года', ' лет ', ' лет', 'г.р.', '(г.р.),', 'лет)', 'лет,']
        for word in age_dict:
            age_words = initial_title.find(word)
            if age_words == -1:
                pass
            else:
                after_age = max(after_age, age_words + len(word))

        if after_age > 0:
            address_string = initial_title[after_age:].strip()
        else:
            numbers = [int(float(s)) for s in re.findall(r'\d*\d', initial_title)]
            if numbers and numbers[0]:
                age_words = initial_title.find(str(numbers[0]))
                if age_words == -1:
                    address_string = initial_title
                else:
                    after_age = age_words + len(str(numbers[0]))
                    address_string = initial_title[after_age:].strip()
            else:
                address_string = initial_title

        # ABOVE is not optimized - but with this part ages are excluded better (for cases when there are 2 persons)
        trigger_of_age_mentions = True

        while trigger_of_age_mentions:
            trigger_of_age_mentions = False
            for word in age_dict:
                if address_string.find(word) > -1:
                    trigger_of_age_mentions = True
                    after_age = address_string.find(word) + len(word)
                    address_string = address_string[after_age:]

        useless_symbols = {'.', ',', ' ', ':', ';' '!', ')'}
        trigger_of_useless_symbols = True

        while trigger_of_useless_symbols:
            trigger_of_useless_symbols = False
            for word in useless_symbols:
                if address_string[0 : len(word)] == word:
                    trigger_of_useless_symbols = True
                    address_string = address_string[len(word) :]

        # case when there's "г.о." instead of "городской округ"
        if address_string.find('г.о.') != -1:
            address_string = address_string.replace('г.о.', 'городской округ')

        # case when there's "муниципальный округ"
        if address_string.find('м.о.') != -1:
            address_string = address_string.replace('м.о.', 'муниципальный округ')

        # case when 'мкрн' or 'мкр'
        if address_string.find('мкрн') != -1:
            address_string = address_string.replace('мкрн', '')
        if address_string.find('мкр') != -1:
            address_string = address_string.replace('мкр', '')

        # case with 'р-н' and 'АО'
        if address_string.find('р-н') != -1 and address_string.find('АО') != -1:
            by_word = address_string.split()
            word_with_ao = None
            for word in by_word:
                if word.find('АО') != -1:
                    word_with_ao = word
            if word_with_ao:
                address_string = address_string.replace(word_with_ao, '')

        # case with 'р-н' or 'р-на' or 'р-он'
        if address_string.find('р-на') != -1:
            address_string = address_string.replace('р-на', 'район')
        if address_string.find('р-н') != -1:
            address_string = address_string.replace('р-н', 'район')
        if address_string.find('р-он') != -1:
            address_string = address_string.replace('р-он', 'район')

        # case with 'обл'
        if address_string.find('обл.') != -1:
            address_string = address_string.replace('обл.', 'область')

        # case with 'НСО'
        if address_string.find('НСО') != -1:
            address_string = address_string.replace('НСО', 'Новосибирская область')

        # case with 'МО'
        if address_string.find('МО') != -1:
            mo_dict = {' МО ', ' МО,'}
            for word in mo_dict:
                if address_string.find(word) != -1:
                    address_string = address_string.replace(word, 'Московская область')
            if address_string[-3:] == ' МО':
                address_string = address_string[:-3] + ' Московская область'

        # case with 'ЛО'
        if address_string.find('ЛО') != -1:
            mo_dict = {' ЛО ', ' ЛО,'}
            for word in mo_dict:
                if address_string.find(word) != -1:
                    address_string = address_string.replace(word, 'Ленинградская область')
            if address_string[-3:] == ' ЛО':
                address_string = address_string[:-3] + ' Ленинградская область'

        # in case "г.Сочи"
        if address_string.find('г.Сочи') != -1:
            address_string = address_string.replace('г.Сочи', 'Сочи')
        if address_string.find('г. Сочи') != -1:
            address_string = address_string.replace('г. Сочи', 'Сочи')

        # case with 'района'
        if address_string.find('района') != -1:
            by_word = address_string.split()
            prev_word = None
            this_word = None
            for k in range(len(by_word) - 1):
                if by_word[k + 1] == 'района':
                    prev_word = by_word[k]
                    this_word = by_word[k + 1]
                    break
            if prev_word and this_word:
                address_string = address_string.replace(prev_word, prev_word[:-3] + 'ий')
                address_string = address_string.replace(this_word, this_word[:-1])

        # case with 'области'
        if address_string.find('области') != -1:
            by_word = address_string.split()
            prev_word = None
            this_word = None
            for k in range(len(by_word) - 1):
                if by_word[k + 1] == 'области':
                    prev_word = by_word[k]
                    this_word = by_word[k + 1]
                    break
            if prev_word and this_word:
                address_string = address_string.replace(prev_word, prev_word[:-2] + 'ая')
                address_string = address_string.replace(this_word, this_word[:-1] + 'ь')

        # add all the cases ABOVE
        # delete garbage in the beginning of string
        try:
            first_num = re.search(r'\d', address_string).start()
        except:  # noqa
            first_num = 0
        try:
            first_letter = re.search(r'[а-яА-Я]', address_string).start()
        except:  # noqa
            first_letter = 0

        new_start = max(first_num, first_letter)

        if address_string.lower().find('г. москва') != -1 or address_string.lower().find('г.москва') != -1:
            address_string = address_string.replace('г.', '')

        # add Russia to be sure
        # Openstreetmap.org treats Krym as Ukraine - so for search purposes Russia is avoided
        if (
            address_string
            and address_string.lower().find('крым') == -1
            and address_string.lower().find('севастополь') == -1
        ):
            address_string = address_string[new_start:] + ', Россия'

        # case - first "с.", "п." and "д." are often misinterpreted - so it's easier to remove it
        wrong_first_symbols_dict = {
            ' ',
            ',',
            ')',
            '.',
            'с.',
            'д.',
            'п.',
            'г.',
            'гп',
            'пос.',
            'уч-к',
            'р,',
            'р.',
            'г,',
            'ст.',
            'л.',
            'дер ',
            'дер.',
            'пгт ',
            'ж/д',
            'б/о',
            'пгт.',
            'х.',
            'ст-ца',
            'с-ца',
            'стан.',
        }

        trigger_of_wrong_symbols = True

        while trigger_of_wrong_symbols:
            this_iteration_bring_no_changes = True

            for wrong_symbols in wrong_first_symbols_dict:
                if address_string[: len(wrong_symbols)] == wrong_symbols:
                    # if the first symbols are from wrong symbols list - we delete them
                    address_string = address_string[len(wrong_symbols) :]
                    this_iteration_bring_no_changes = False

            if this_iteration_bring_no_changes:
                trigger_of_wrong_symbols = False

        # ONE-TIME EXCEPTIONS:
        if address_string.find('г. Сольцы, Новгородская обл. – г. Санкт-Петербург'):
            address_string = address_string.replace(
                'г. Сольцы, Новгородская область – г. Санкт-Петербург', 'г. Сольцы, Новгородская область'
            )
        if address_string.find('Орехово-Зуевский район'):
            address_string = address_string.replace('Орехово-Зуевский район', 'Орехово-Зуевский городской округ')
        if address_string.find('НТ Нефтяник'):
            address_string = address_string.replace('СНТ Нефтяник', 'СНТ Нефтянник')
        if address_string.find('Коченевский'):
            address_string = address_string.replace('Коченевский', 'Коченёвский')
        if address_string.find('Самара - с. Красный Яр'):
            address_string = address_string.replace('г. Самара - с. Красный Яр', 'Красный Яр')
        if address_string.find('укреево-Плессо'):
            address_string = address_string.replace('Букреево-Плессо', 'Букреево Плёсо')
        if address_string.find('Москва Москва: Юго-Западный АО, '):
            address_string = address_string.replace('г.Москва Москва: Юго-Западный АО, ', 'ЮЗАО, Москва, ')
        if address_string.find(' Луховицы - д.Алтухово'):
            address_string = address_string.replace(' Луховицы - д. Алтухово, Зарайский городской округ,', 'Луховицы')
        if address_string.find('Сагкт-Петербург'):
            address_string = address_string.replace('Сагкт-Петербург', 'Санкт-Петербург')
        if address_string.find('Краснозерский'):
            address_string = address_string.replace('Краснозерский', 'Краснозёрский')
        if address_string.find('Толмачевское'):
            address_string = address_string.replace('Толмачевское', 'Толмачёвское')
        if address_string.find('Кочевский'):
            address_string = address_string.replace('Кочевский', 'Кочёвский')
        if address_string.find('Чесцы'):
            address_string = address_string.replace('Чесцы', 'Часцы')

        return address_string

    def save_place_in_psql(db2, address_string):
        """save a link search to address in sql table search_places"""

        try:
            with db2.connect() as conn:
                # check if this record already exists
                stmt = sqlalchemy.text(
                    """SELECT search_id FROM search_places
                    WHERE search_id=:a AND address=:b;"""
                )
                prev_data = conn.execute(stmt, a=search_num, b=address_string).fetchone()

                # if it's a new info
                if not prev_data:
                    stmt = sqlalchemy.text(
                        """INSERT INTO search_places (search_id, address, timestamp)
                        VALUES (:a, :b, :c); """
                    )
                    conn.execute(stmt, a=search_num, b=address_string, c=datetime.now())

                conn.close()

        except Exception as e7:
            logging.info('DBG.P.EXC.110: ')
            logging.exception(e7)
            notify_admin('ERROR: saving place to psql failed: ' + address_string + ', ' + search_num)

        return None

    # DEBUG - function execution time counter
    func_start = datetime.now()

    url_to_topic = f'https://lizaalert.org/forum/viewtopic.php?t={search_num}'

    lat = 0
    lon = 0
    coord_type = ''
    search_code_blocks = None
    title = None

    try:
        r = requests_session.get(url_to_topic)  # noqa
        if not visibility_check(r, search_num):
            return [lat, lon, coord_type]

        soup = BeautifulSoup(r.content, features='html.parser')

        # parse title
        title_code = soup.find('h2', {'class': 'topic-title'})
        title = title_code.text

        # open the first post
        search_code_blocks = soup.find('div', 'content')

        if not search_code_blocks:
            return [lat, lon, coord_type]

        # removing <br> tags
        for e in search_code_blocks.findAll('br'):
            e.extract()

    except Exception as e:
        logging.info(f'unable to parse a specific thread with address {url_to_topic} error is {repr(e)}')

    if search_code_blocks:
        # FIRST CASE = THERE ARE COORDINATES w/ a WORD Coordinates
        try:
            # make an independent variable
            a = copy.copy(search_code_blocks)

            # remove a text with strike-through
            b = a.find_all('span', {'style': 'text-decoration:line-through'})
            for i in range(len(b)):
                b[i].decompose()

            # preparing a list of 100-character strings which starts with Coord mentioning
            e = []
            i = 0
            f = str(a).lower()

            while i < len(f):
                if f[i:].find('коорд') > 0:
                    d = i + f[i:].find('коорд')
                    e.append(f[d : (d + 100)])
                    if d == 0 or d == -1:
                        i = len(f)
                    else:
                        i = d + 1
                else:
                    i = len(f)

            # extract exact numbers & match if they look like coordinates
            for i in range(len(e)):
                g = [float(s) for s in re.findall(r'-?\d+\.?\d*', e[i])]
                if len(g) > 1:
                    for j in range(len(g) - 1):
                        try:
                            # Majority of coords in RU: lat in [40-80], long in [20-180], expected min format = XX.XXX
                            if (
                                3 < (g[j] // 10) < 8
                                and len(str(g[j])) > 5
                                and 1 < (g[j + 1] // 10) < 19
                                and len(str(g[j + 1])) > 5
                            ):
                                lat = g[j]
                                lon = g[j + 1]
                                coord_type = '1. coordinates w/ word coord'
                        except Exception as e2:
                            logging.info('DBG.P.36.EXC. Coords-1:')
                            logging.exception(e2)

        except Exception as e:
            logging.info('Exception happened')
            logging.exception(e)
            pass

        # SECOND CASE = THERE ARE COORDINATES w/o a WORD Coordinates
        if lat == 0:
            # make an independent variable
            a = copy.copy(search_code_blocks)

            try:
                # remove a text with strike-through
                b = a.find_all('span', {'style': 'text-decoration:line-through'})
                for i in range(len(b)):
                    b[i].decompose()

                # removing <span> tags
                for e in a.findAll('span'):
                    e.replace_with(e.text)

                # removing <img> tags
                for e in a.findAll('img'):
                    e.extract()

                # removing <a> tags
                for e in a.findAll('a'):
                    e.extract()

                # removing <strong> tags
                for e in a.findAll('strong'):
                    e.replace_with(e.text)

                # converting to string
                b = re.sub(r'\n\s*\n', r' ', a.get_text().strip(), flags=re.M)
                c = re.sub(r'\n', r' ', b)
                g = [float(s) for s in re.findall(r'-?\d+\.?\d*', c)]
                if len(g) > 1:
                    for j in range(len(g) - 1):
                        try:
                            # Majority of coords in RU: lat in [40-80], long in [20-180], expected min format = XX.XXX
                            if (
                                3 < (g[j] // 10) < 8
                                and len(str(g[j])) > 5
                                and 1 < (g[j + 1] // 10) < 19
                                and len(str(g[j + 1])) > 5
                            ):
                                lat = g[j]
                                lon = g[j + 1]
                                coord_type = '2. coordinates w/o word coord'
                        except Exception as e2:
                            logging.info('DBG.P.36.EXC. Coords-2:')
                            logging.exception(e2)
            except Exception as e:
                logging.info('Exception 2')
                logging.exception(e)
                pass

        # THIRD CASE = DELETED COORDINATES
        if lat == 0:
            # make an independent variable
            a = copy.copy(search_code_blocks)

            try:
                # get a text with strike-through
                a = a.find_all('span', {'style': 'text-decoration:line-through'})
                if a:
                    for line in a:
                        b = re.sub(r'\n\s*\n', r' ', line.get_text().strip(), flags=re.M)
                        c = re.sub(r'\n', r' ', b)
                        g = [float(s) for s in re.findall(r'-?\d+\.?\d*', c)]
                        if len(g) > 1:
                            for j in range(len(g) - 1):
                                try:
                                    # Majority of coords in RU: lat in [40-80], long in [20-180],
                                    # expected minimal format = XX.XXX
                                    if (
                                        3 < (g[j] // 10) < 8
                                        and len(str(g[j])) > 5
                                        and 1 < (g[j + 1] // 10) < 19
                                        and len(str(g[j + 1])) > 5
                                    ):
                                        lat = g[j]
                                        lon = g[j + 1]
                                        coord_type = '3. deleted coord'
                                except Exception as e2:
                                    logging.info('DBG.P.36.EXC. Coords-1:')
                                    logging.exception(e2)
            except Exception as e:
                logging.info('exception:')
                logging.exception(e)
                pass

    # FOURTH CASE = COORDINATES FROM ADDRESS
    if lat == 0:
        try:
            address = parse_address_from_title(title)
            if address:
                save_place_in_psql(db, address)
                lat, lon = get_coordinates(db, address)
                if lat and lon:
                    coord_type = '4. coordinates by address'
            else:
                logging.info(f'No address was found for search {search_num}, title {title}')
        except Exception as e5:
            logging.info('DBG.P.42.EXC:')
            logging.exception(e5)

    # DEBUG - function execution time counter
    func_finish = datetime.now()
    func_execution_time_ms = func_finish - func_start
    logging.info(f'the coordinates for {search_num=} are defined as {lat}, {lon}, {coord_type}')
    logging.info(f'DBG.P.5.parse_coordinates() exec time: {func_execution_time_ms}')

    return [lat, lon, coord_type]


def update_coordinates(db, list_of_search_objects):
    """Record search coordinates to PSQL"""

    for search in list_of_search_objects:
        search_id = search.topic_id
        search_status = search.new_status

        if search_status not in {'Ищем', 'СТОП'}:
            continue

        logging.info(f'search coordinates should be saved for {search_id=}')
        coords = parse_coordinates(db, search_id)

        with db.connect() as conn:
            stmt = sqlalchemy.text(
                'SELECT latitude, longitude, coord_type FROM search_coordinates WHERE search_id=:a LIMIT 1;'
            )
            old_coords = conn.execute(stmt, a=search_id).fetchone()

            if coords[0] != 0 and coords[1] != 0:
                if old_coords is None:
                    stmt = sqlalchemy.text(
                        """INSERT INTO search_coordinates (search_id, latitude, longitude, coord_type, upd_time)
                        VALUES (:a, :b, :c, :d, CURRENT_TIMESTAMP); """
                    )
                    conn.execute(stmt, a=search_id, b=coords[0], c=coords[1], d=coords[2])
                else:
                    # when coords are in search_coordinates table
                    old_lat, old_lon, old_type = old_coords
                    do_update = False
                    if not old_type:
                        do_update = True
                    elif not (old_type[0] != '4' and coords[2][0] == '4'):
                        do_update = True
                    elif old_type[0] == '4' and coords[2][0] == '4' and (old_lat != coords[0] or old_lon != coords[1]):
                        do_update = True

                    if do_update:
                        stmt = sqlalchemy.text(
                            """UPDATE search_coordinates SET latitude=:a, longitude=:b, coord_type=:c,
                            upd_time=CURRENT_TIMESTAMP WHERE search_id=:d; """
                        )
                        conn.execute(stmt, a=coords[0], b=coords[1], c=coords[2], d=search_id)

            # case when coords are not defined, but there were saved coords type 1 or 2 – so we need to mark as deleted
            elif old_coords and old_coords[2] and old_coords[2][0] in {'1', '2'}:
                stmt = sqlalchemy.text(
                    """UPDATE search_coordinates SET coord_type=:a, upd_time=CURRENT_TIMESTAMP
                       WHERE search_id=:b; """
                )
                conn.execute(stmt, a=coords[2], b=search_id)

            conn.close()

    return None


def publish_to_pubsub(topic_name, message):
    """publish a message to specific pub/sub topic"""

    global project_id

    # Prepare to turn to the existing pub/sub topic
    topic_path = publisher.topic_path(project_id, topic_name)

    # Prepare the message
    message_json = json.dumps(
        {
            'data': {'message': message},
        }
    )
    message_bytes = message_json.encode('utf-8')

    # Publish a message
    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info(
            f'Pub/sub message to topic {topic_name} with event_id = {publish_future.result()} has '
            f'been triggered. Content: {message}'
        )

    except Exception as e:
        logging.info(f'Not able to send pub/sub message: {message}')
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


def process_pubsub_message(event):
    """convert incoming pub/sub message into regular data"""

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
        logging.info('received_message_from_pubsub: ' + str(received_message_from_pubsub))
    elif 'message' in event:
        received_message_from_pubsub = base64.b64decode(event).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
        logging.info(received_message_from_pubsub)
    encoded_to_ascii = eval(received_message_from_pubsub)
    logging.info('encoded_to_ascii: ' + str(encoded_to_ascii))
    try:
        data_in_ascii = encoded_to_ascii['data']
        logging.info('data_in_ascii: ' + str(data_in_ascii))
        message_in_ascii = data_in_ascii['message']
        logging.info('message_in_ascii: ' + str(message_in_ascii))
    except Exception as es:
        message_in_ascii = None
        logging.info('exception happened: ')
        logging.exception(str(es))

    return message_in_ascii


def sql_connect():
    """set the connection pool to cloud sql"""

    db_user = get_secrets('cloud-postgres-username')
    db_pass = get_secrets('cloud-postgres-password')
    db_name = get_secrets('cloud-postgres-db-name')
    db_conn = get_secrets('cloud-postgres-connection-name')
    db_socket_dir = '/cloudsql'

    db_config = {
        'pool_size': 5,
        'max_overflow': 0,
        'pool_timeout': 0,  # seconds
        'pool_recycle': 120,  # seconds
    }

    pool = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL(
            'postgresql+pg8000',
            username=db_user,
            password=db_pass,
            database=db_name,
            query={'unix_sock': '{}/{}/.s.PGSQL.5432'.format(db_socket_dir, db_conn)},
        ),
        **db_config,
    )
    pool.dialect.description_encoding = None

    return pool


def get_secrets(secret_request):
    """get the secret stored in Google Cloud Secrets"""

    name = f'projects/{project_id}/secrets/{secret_request}/versions/latest'
    response = client.access_secret_version(name=name)

    return response.payload.data.decode('UTF-8')


def define_start_time_of_search(blocks):
    """define search start time & date"""

    start_datetime_as_string = blocks.find('div', 'topic-poster responsive-hide left-box')
    start_datetime = start_datetime_as_string.time['datetime']

    return start_datetime


def profile_get_type_of_activity(text_of_activity):
    """get the status of the search activities: is there HQ, is there Active duties"""

    activity_type = []
    hq = None

    # Cases with HQ
    if text_of_activity.lower().find('штаб свернут') > -1:
        hq = 'no'
    elif text_of_activity.lower().find('штаб свёрнут') > -1:
        hq = 'no'
    elif text_of_activity.lower().find('штаб свëрнут') > -1:
        hq = 'no'

    if hq == 'no':
        activity_type.append('9 - hq closed')
    else:
        if text_of_activity.lower().find('сбор') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('штаб работает') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('выезд сейчас') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('внимание, выезд') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('внимание выезд') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('внимание! выезд') > -1:
            hq = 'now'

        if hq == 'now':
            activity_type.append('1 - hq now')
        else:
            if text_of_activity.lower().find('штаб мобильный') > -1:
                hq = 'mobile'

            if hq == 'mobile':
                activity_type.append('2 - hq mobile')
            else:
                if text_of_activity.lower().find('выезд ожидается') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('ожидается выезд') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('выезд планируется') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('планируется выезд') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('готовится выезд') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('выезд готовится') > -1:
                    hq = 'will'

                if hq == 'will':
                    activity_type.append('1 - hq will')

    # Cases with Autonom
    if hq not in {'mobile, now, will'}:
        if text_of_activity.lower().find('опрос') > -1:
            hq = 'autonom'
        if text_of_activity.lower().find('оклейка') > -1:
            hq = 'autonom'
    if text_of_activity.lower().find('автоном') > -1 and not text_of_activity.lower().find('нет автоном'):
        hq = 'autonom'
    elif text_of_activity.lower().find('двойк') > -1:
        hq = 'autonom'

    if hq == 'autonom':
        activity_type.append('6 - autonom')

    # Specific Tasks
    if text_of_activity.lower().find('забрать оборудование') > -1:
        activity_type.append('3 - hardware logistics')
    elif text_of_activity.lower().find('забрать комплект оборудования') > -1:
        activity_type.append('3 - hardware logistics')

    activity_type.sort()

    return activity_type


def profile_get_managers(text_of_managers):
    """define list of managers out of profile plain text"""

    managers = []

    try:
        list_of_lines = text_of_managers.split('\n')

        # Define the block of text with managers which starts with ------
        zero_line = None
        for i in range(len(list_of_lines)):
            if list_of_lines[i].find('--------') > -1:
                zero_line = i + 1
                break

        # If there's a telegram link in a new line - to move it to prev line
        for i in range(len(list_of_lines) - 1):
            if list_of_lines[i + 1][0:21] == 'https://telegram.im/@':
                list_of_lines[i] += ' ' + list_of_lines[i + 1]
                list_of_lines[i + 1] = ''
            if list_of_lines[i + 1][0:14] == 'https://t.me/':
                list_of_lines[i] += ' ' + list_of_lines[i + 1]
                list_of_lines[i + 1] = ''

        list_of_roles = [
            'Координатор-консультант',
            'Координатор',
            'Инфорг',
            'Старшая на месте',
            'Старший на месте',
            'ДИ ',
            'СНМ',
        ]

        for line in list_of_lines[zero_line:]:
            line_by_word = line.split()
            for i in range(len(line_by_word)):
                for role in list_of_roles:
                    if str(line_by_word[i]).find(role) > -1:
                        manager_line = line_by_word[i]
                        for j in range(len(line_by_word) - i - 1):
                            if line_by_word[i + j + 1].find(role) == -1:
                                manager_line += ' ' + str(line_by_word[i + j + 1])
                            else:
                                break

                        # Block of minor RARE CASE corrections
                        manager_line = manager_line.replace(',,', ',')
                        manager_line = manager_line.replace(':,', ':')
                        manager_line = manager_line.replace(', ,', ',')
                        manager_line = manager_line.replace('  ', ' ')

                        managers.append(manager_line)
                        break

        # replace telegram contacts with nice links
        for manager in managers:
            for word in manager.split(' '):
                nickname = None

                if word.find('https://telegram.im/') > -1:
                    nickname = word[20:]

                if word.find('https://t.me/') > -1:
                    nickname = word[13:]

                if nickname:
                    # tip: sometimes there are two @ in the beginning (by human mistake)
                    while nickname[0] == '@':
                        nickname = nickname[1:]

                    # tip: sometimes the last symbol is wrong
                    while nickname[-1:] in {'.', ',', ' '}:
                        nickname = nickname[:-1]

                    manager = manager.replace(word, f'<a href="https://t.me/{nickname}">@{nickname}</a>')

        # FIXME – for debug
        logging.info('DBG.P.101.Managers_list:')
        for manager in managers:
            logging.info(manager)
        # FIXME ^^^

    except Exception as e:
        logging.info('DBG.P.102.EXC:')
        logging.exception(e)

    return managers


def parse_search_profile(search_num):
    """get search activities list"""

    global block_of_profile_rough_code
    global requests_session

    url_beginning = 'https://lizaalert.org/forum/viewtopic.php?t='
    url_to_topic = url_beginning + str(search_num)

    try:
        r = requests_session.get(url_to_topic)  # noqa
        if not visibility_check(r, search_num):
            return None

        soup = BeautifulSoup(r.content, features='html.parser')

    except Exception as e:
        logging.info(f'DBG.P.50.EXC: unable to parse a specific Topic with address: {url_to_topic} error:')
        logging.exception(e)
        soup = None

    # open the first post
    block_of_profile_rough_code = soup.find('div', 'content')

    # excluding <line-through> tags
    for deleted in block_of_profile_rough_code.findAll('span', {'style': 'text-decoration:line-through'}):
        deleted.extract()

    # add telegram links to text (to be sure next step won't cut these links), type 1
    for a_tag in block_of_profile_rough_code.find_all('a'):
        if a_tag.get('href')[0:20] == 'https://telegram.im/':
            a_tag.replace_with(a_tag['href'])

    # add telegram links to text (to be sure next step won't cut these links), type 2
    for a_tag in block_of_profile_rough_code.find_all('a'):
        if a_tag.get('href')[0:13] == 'https://t.me/':
            a_tag.replace_with(a_tag['href'])

    left_text = block_of_profile_rough_code.text.strip()

    """DEBUG"""
    logging.info('DBG.Profile:' + left_text)

    return left_text


def make_api_call(function: str, data: dict) -> dict:
    """makes an API call to another Google Cloud Function"""

    # function we're turing to "title_recognize"
    endpoint = f'https://europe-west3-lizaalert-bot-01.cloudfunctions.net/{function}'

    # required magic for Google Cloud Functions Gen2 to invoke each other
    audience = endpoint
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)
    headers = {'Authorization': f'Bearer {id_token}', 'Content-Type': 'application/json'}

    r = requests.post(endpoint, json=data, headers=headers)
    content = r.json()

    return content


def parse_one_folder(db, folder_id):
    """parse forum folder with searches' summaries"""

    global requests_session

    topic_type_dict = {'search': 0, 'search reverse': 1, 'search patrol': 2, 'search training': 3, 'event': 10}

    # TODO - "topics_summary_in_folder" – is an old type of list, which was deprecated as an outcome of this script,
    #  now we need to delete it completely
    topics_summary_in_folder = []
    titles_and_num_of_replies = []
    folder_summary = []
    current_datetime = datetime.now()
    url = f'https://lizaalert.org/forum/viewforum.php?f={folder_id}'
    try:
        r = requests_session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa

        only_tag = SoupStrainer('div', {'class': 'forumbg'})
        soup = BeautifulSoup(r.content, features='lxml', parse_only=only_tag)
        del r  # trying to free up memory
        search_code_blocks = soup.find_all('dl', 'row-item')
        del soup  # trying to free up memory

        for i, data_block in enumerate(search_code_blocks):
            # First block is always not one we want
            if i == 0:
                continue

            # In rare cases there are aliases from other folders, which have static titles – and we're avoiding them
            if str(data_block).find('<dl class="row-item topic_moved">') > -1:
                continue

            # Current block which contains everything regarding certain search
            search_title_block = data_block.find('a', 'topictitle')
            # rare case: cleaning [size][b]...[/b][/size] tags
            search_title = re.sub(r'\[/?(b|size.{0,6}|color.{0,10})]', '', search_title_block.next_element)
            search_id = int(re.search(r'(?<=&t=)\d{2,8}', search_title_block['href']).group())
            search_replies_num = int(data_block.find('dd', 'posts').next_element)
            start_datetime = define_start_time_of_search(data_block)

            data = {'title': search_title}
            try:
                title_reco_response = make_api_call('title_recognize', data)

                if (
                    title_reco_response
                    and 'status' in title_reco_response.keys()
                    and title_reco_response['status'] == 'ok'
                ):
                    title_reco_dict = title_reco_response['recognition']
                else:
                    title_reco_dict = {'topic_type': 'UNRECOGNIZED'}

                logging.info(f'{title_reco_dict=}')

                # NEW exclude non-relevant searches
                if title_reco_dict['topic_type'] in {
                    'search',
                    'search training',
                    'search reverse',
                    'search patrol',
                    'event',
                }:
                    # FIXME – 06.11.2023 – work to delete function "define_family_name_from_search_title_new"
                    if title_reco_dict['topic_type'] == 'event':
                        person_fam_name = None
                    else:
                        try:
                            person_fam_name = title_reco_dict['persons']['total_name']  # noqa
                        except Exception as ex:
                            logging.exception(ex)
                            notify_admin(repr(ex))
                            person_fam_name = 'БВП'
                    # FIXME ^^^

                    search_summary_object = SearchSummary(
                        parsed_time=current_datetime,
                        topic_id=search_id,
                        title=search_title,
                        start_time=start_datetime,
                        num_of_replies=search_replies_num,
                        name=person_fam_name,
                        folder_id=folder_id,
                    )
                    search_summary_object.topic_type = title_reco_dict['topic_type']

                    search_summary_object.topic_type_id = topic_type_dict[search_summary_object.topic_type]

                    if 'persons' in title_reco_dict.keys():
                        if 'total_display_name' in title_reco_dict['persons'].keys():
                            search_summary_object.display_name = title_reco_dict['persons']['total_display_name']
                        if 'age_min' in title_reco_dict['persons'].keys():
                            search_summary_object.age_min = title_reco_dict['persons']['age_min']
                            search_summary_object.age = title_reco_dict['persons']['age_min']  # Due to the field
                            # "age" in searches which is integer, so we cannot indicate a range
                        if 'age_max' in title_reco_dict['persons'].keys():
                            search_summary_object.age_max = title_reco_dict['persons']['age_max']

                    if 'status' in title_reco_dict.keys():
                        search_summary_object.new_status = title_reco_dict['status']
                        search_summary_object.status = title_reco_dict['status']

                    if 'locations' in title_reco_dict.keys():
                        list_of_location_cities = [x['address'] for x in title_reco_dict['locations']]
                        list_of_location_coords = []
                        for location_city in list_of_location_cities:
                            city_lat, city_lon = get_coordinates(db, location_city)
                            if city_lat and city_lon:
                                list_of_location_coords.append([city_lat, city_lon])
                        search_summary_object.locations = list_of_location_coords

                    folder_summary.append(search_summary_object)

                    search_summary = [
                        current_datetime,
                        search_id,
                        search_summary_object.status,
                        search_title,
                        '',
                        start_datetime,
                        search_replies_num,
                        search_summary_object.age_min,
                        person_fam_name,
                        folder_id,
                    ]
                    topics_summary_in_folder.append(search_summary)

                    parsed_wo_date = [search_title, search_replies_num]
                    titles_and_num_of_replies.append(parsed_wo_date)

            except Exception as e:
                logging.info(f'TEMP - THIS BIG ERROR HAPPENED, {data=}')
                notify_admin(f'TEMP - THIS BIG ERROR HAPPENED, {data=}, {type(data)=}')
                logging.error(e)
                logging.exception(e)

        del search_code_blocks

    # To catch timeout once a day in the night
    except (requests.exceptions.Timeout, ConnectionResetError, Exception) as e:
        logging.exception(e)
        topics_summary_in_folder = []
        folder_summary = []

    logging.info(f'folder = {folder_id}, old_topics_summary = {topics_summary_in_folder}')

    return titles_and_num_of_replies, folder_summary


def visibility_check(r, topic_id):
    """check topic's visibility: if hidden or deleted"""

    check_content = copy.copy(r.content)
    check_content = check_content.decode('utf-8')
    check_content = None if re.search(r'502 Bad Gateway', check_content) else check_content
    site_unavailable = False if check_content else True
    topic_deleted = True if check_content and re.search(r'Запрошенной темы не существует', check_content) else False
    topic_hidden = (
        True
        if check_content and re.search(r'Для просмотра этого форума вы должны быть авторизованы', check_content)
        else False
    )
    if site_unavailable:
        return False
    elif topic_deleted or topic_hidden:
        visibility = 'deleted' if topic_deleted else 'hidden'
        publish_to_pubsub('topic_for_topic_management', {'topic_id': topic_id, 'visibility': visibility})
        return False

    return True


def parse_one_comment(db, search_num, comment_num):
    """parse all details on a specific comment in topic (by sequence number)"""

    global requests_session

    comment_url = f'https://lizaalert.org/forum/viewtopic.php?&t={search_num}&start={comment_num}'
    there_are_inforg_comments = False

    try:
        r = requests_session.get(comment_url)  # noqa

        if not visibility_check(r, search_num):
            return False

        soup = BeautifulSoup(r.content, features='lxml')
        search_code_blocks = soup.find('div', 'post')

        # finding USERNAME
        comment_author_block = search_code_blocks.find('a', 'username')
        if not comment_author_block:
            comment_author_block = search_code_blocks.find('a', 'username-coloured')
        try:
            comment_author_nickname = comment_author_block.text
        except Exception as e:
            logging.info(f'exception for search={search_num} and comment={comment_num}')
            logging.exception(e)
            comment_author_nickname = 'unidentified_username'

        if comment_author_nickname[:6].lower() == 'инфорг' and comment_author_nickname != 'Инфорг кинологов':
            there_are_inforg_comments = True

        # finding LINK to user profile
        try:
            comment_author_link = int(''.join(filter(str.isdigit, comment_author_block['href'][36:43])))

        except Exception as e:
            logging.info(
                'Here is an exception 9 for search '
                + str(search_num)
                + ', and comment '
                + str(comment_num)
                + ' error: '
                + repr(e)
            )
            try:
                comment_author_link = int(
                    ''.join(filter(str.isdigit, search_code_blocks.find('a', 'username-coloured')['href'][36:43]))
                )
            except Exception as e2:
                logging.info('Here is an exception 10' + repr(e2))
                comment_author_link = 'unidentified_link'

        # finding the global comment id
        comment_forum_global_id = int(search_code_blocks.find('p', 'author').findNext('a')['href'][-6:])

        # finding TEXT of the comment
        comment_text_0 = search_code_blocks.find('div', 'content')
        try:
            # external_span = comment_text_0.blockquote.extract()
            comment_text_1 = comment_text_0.text
        except Exception as e:
            logging.info(f'exception for search={search_num} and comment={comment_num}')
            logging.exception(e)
            comment_text_1 = comment_text_0.text
        comment_text = ' '.join(comment_text_1.split())

        # Define exclusions (comments of Inforg with "резерв" and "рассылка билайн"
        ignore = False
        if there_are_inforg_comments:
            if comment_text.lower()[0:6] == 'резерв' or comment_text.lower()[0:15] == 'рассылка билайн':
                ignore = True

        with db.connect() as conn:
            if comment_text:
                if not ignore:
                    stmt = sqlalchemy.text(
                        """INSERT INTO comments (comment_url, comment_text, comment_author_nickname,
                        comment_author_link, search_forum_num, comment_num, comment_global_num)
                        VALUES (:a, :b, :c, :d, :e, :f, :g); """
                    )
                    conn.execute(
                        stmt,
                        a=comment_url,
                        b=comment_text,
                        c=comment_author_nickname,
                        d=comment_author_link,
                        e=search_num,
                        f=comment_num,
                        g=comment_forum_global_id,
                    )
                else:
                    stmt = sqlalchemy.text(
                        """INSERT INTO comments (comment_url, comment_text, comment_author_nickname,
                        comment_author_link, search_forum_num, comment_num, notification_sent)
                        VALUES (:a, :b, :c, :d, :e, :f, :g); """
                    )
                    conn.execute(
                        stmt,
                        a=comment_url,
                        b=comment_text,
                        c=comment_author_nickname,
                        d=comment_author_link,
                        e=search_num,
                        f=comment_num,
                        g='n',
                    )

            conn.close()

    except ConnectionResetError:
        logging.info('There is a connection error')

    return there_are_inforg_comments


def update_change_log_and_searches(db, folder_num):
    """update of SQL tables 'searches' and 'change_log' on the changes vs previous parse"""

    change_log_ids = []

    class ChangeLogLine:
        def __init__(
            self, parsed_time=None, topic_id=None, changed_field=None, new_value=None, parameters=None, change_type=None
        ):
            self.parsed_time = parsed_time
            self.topic_id = topic_id
            self.changed_field = changed_field
            self.new_value = new_value
            self.parameters = parameters
            self.change_type = change_type

    # DEBUG - function execution time counter
    func_start = datetime.now()

    with db.connect() as conn:
        sql_text = sqlalchemy.text(
            """SELECT search_forum_num, parsed_time, status, forum_search_title, search_start_time,
            num_of_replies, family_name, age, id, forum_folder_id, topic_type, display_name, age_min, age_max,
            status, city_locations, topic_type_id
            FROM forum_summary_snapshot WHERE
            forum_folder_id = :a; """
        )
        snapshot = conn.execute(sql_text, a=folder_num).fetchall()
        curr_snapshot_list = []
        for line in snapshot:
            snapshot_line = SearchSummary()
            (
                snapshot_line.topic_id,
                snapshot_line.parsed_time,
                snapshot_line.status,
                snapshot_line.title,
                snapshot_line.start_time,
                snapshot_line.num_of_replies,
                snapshot_line.name,
                snapshot_line.age,
                snapshot_line.id,
                snapshot_line.folder_id,
                snapshot_line.topic_type,
                snapshot_line.display_name,
                snapshot_line.age_min,
                snapshot_line.age_max,
                snapshot_line.new_status,
                snapshot_line.locations,
                snapshot_line.topic_type_id,
            ) = list(line)

            curr_snapshot_list.append(snapshot_line)

        # TODO - in future: should the number of searches be limited? Probably to JOIN change_log and WHERE folder=...
        searches_full_list = conn.execute(
            """SELECT search_forum_num, parsed_time, status, forum_search_title, search_start_time,
            num_of_replies, family_name, age, id, forum_folder_id,
            topic_type, display_name, age_min, age_max, status, city_locations, topic_type_id FROM searches;"""
        ).fetchall()
        prev_searches_list = []
        for searches_line in searches_full_list:
            search = SearchSummary()
            (
                search.topic_id,
                search.parsed_time,
                search.status,
                search.title,
                search.start_time,
                search.num_of_replies,
                search.name,
                search.age,
                search.id,
                search.folder_id,
                search.topic_type,
                search.display_name,
                search.age_min,
                search.age_max,
                search.new_status,
                search.locations,
                search.topic_type_id,
            ) = list(searches_line)
            prev_searches_list.append(search)

        # FIXME – temp – just to check how many lines
        print(f'TEMP – len of prev_searches_list = {len(prev_searches_list)}')
        if len(prev_searches_list) > 5000:
            logging.info('TEMP - you use too big table Searches, it should be optimized')
        # FIXME ^^^

        """1. move UPD to Change Log"""
        change_log_updates_list = []
        there_are_inforg_comments = False

        for snapshot_line in curr_snapshot_list:
            for searches_line in prev_searches_list:
                if snapshot_line.topic_id != searches_line.topic_id:
                    continue

                if snapshot_line.status != searches_line.status:
                    change_log_line = ChangeLogLine(
                        parsed_time=snapshot_line.parsed_time,
                        topic_id=snapshot_line.topic_id,
                        changed_field='status_change',
                        new_value=snapshot_line.status,
                        parameters='',
                        change_type=1,
                    )

                    change_log_updates_list.append(change_log_line)

                if snapshot_line.title != searches_line.title:
                    change_log_line = ChangeLogLine(
                        parsed_time=snapshot_line.parsed_time,
                        topic_id=snapshot_line.topic_id,
                        changed_field='title_change',
                        new_value=snapshot_line.title,
                        parameters='',
                        change_type=2,
                    )

                    change_log_updates_list.append(change_log_line)

                if snapshot_line.num_of_replies > searches_line.num_of_replies:
                    change_log_line = ChangeLogLine(
                        parsed_time=snapshot_line.parsed_time,
                        topic_id=snapshot_line.topic_id,
                        changed_field='replies_num_change',
                        new_value=snapshot_line.num_of_replies,
                        parameters='',
                        change_type=3,
                    )

                    change_log_updates_list.append(change_log_line)

                    for k in range(snapshot_line.num_of_replies - searches_line.num_of_replies):
                        flag_if_comment_was_from_inforg = parse_one_comment(
                            db, snapshot_line.topic_id, searches_line.num_of_replies + 1 + k
                        )
                        if flag_if_comment_was_from_inforg:
                            there_are_inforg_comments = True

                    if there_are_inforg_comments:
                        change_log_line = ChangeLogLine(
                            parsed_time=snapshot_line.parsed_time,
                            topic_id=snapshot_line.topic_id,
                            changed_field='inforg_replies',
                            new_value=snapshot_line.num_of_replies,
                            parameters='',
                            change_type=4,
                        )

                        change_log_updates_list.append(change_log_line)

        if change_log_updates_list:
            stmt = sqlalchemy.text(
                """INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, parameters,
                change_type) values (:a, :b, :c, :d, :e, :f) RETURNING id;"""
            )

            for line in change_log_updates_list:
                raw_data = conn.execute(
                    stmt,
                    a=line.parsed_time,
                    b=line.topic_id,
                    c=line.changed_field,
                    d=line.new_value,
                    e=line.parameters,
                    f=line.change_type,
                ).fetchone()
                change_log_ids.append(raw_data[0])

        """2. move ADD to Change Log """
        new_topics_from_snapshot_list = []

        for snapshot_line in curr_snapshot_list:
            new_search_flag = 1
            for searches_line in prev_searches_list:
                if snapshot_line.topic_id == searches_line.topic_id:
                    new_search_flag = 0
                    break

            if new_search_flag == 1:
                new_topics_from_snapshot_list.append(snapshot_line)

        change_log_new_topics_list = []

        for snapshot_line in new_topics_from_snapshot_list:
            change_type_id = 0
            change_type_name = 'new_search'

            change_log_line = ChangeLogLine(
                parsed_time=snapshot_line.parsed_time,
                topic_id=snapshot_line.topic_id,
                changed_field=change_type_name,
                new_value=snapshot_line.title,
                parameters='',
                change_type=change_type_id,
            )
            change_log_new_topics_list.append(change_log_line)

        if change_log_new_topics_list:
            stmt = sqlalchemy.text(
                """INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, change_type)
                values (:a, :b, :c, :d, :e) RETURNING id;"""
            )
            for line in change_log_new_topics_list:
                raw_data = conn.execute(
                    stmt,
                    a=line.parsed_time,
                    b=line.topic_id,
                    c=line.changed_field,
                    d=line.new_value,
                    e=line.change_type,
                ).fetchone()
                change_log_ids.append(raw_data[0])

        """3. ADD to Searches"""
        if new_topics_from_snapshot_list:
            stmt = sqlalchemy.text(
                """INSERT INTO searches (search_forum_num, parsed_time, forum_search_title,
                search_start_time, num_of_replies, age, family_name, forum_folder_id, topic_type,
                display_name, age_min, age_max, status, city_locations, topic_type_id)
                VALUES (:a, :b, :d, :e, :f, :g, :h, :i, :j, :k, :l, :m, :n, :o, :p); """
            )
            for line in new_topics_from_snapshot_list:
                conn.execute(
                    stmt,
                    a=line.topic_id,
                    b=line.parsed_time,
                    d=line.title,
                    e=line.start_time,
                    f=line.num_of_replies,
                    g=line.age,
                    h=line.name,
                    i=line.folder_id,
                    j=line.topic_type,
                    k=line.display_name,
                    l=line.age_min,
                    m=line.age_max,
                    n=line.new_status,
                    o=str(line.locations),
                    p=line.topic_type_id,
                )

                search_num = line.topic_id

                parsed_profile_text = parse_search_profile(search_num)
                search_activities = profile_get_type_of_activity(parsed_profile_text)

                logging.info(f'DBG.P.103:Search activities: {search_activities}')

                # mark all old activities as deactivated
                sql_text = sqlalchemy.text(
                    """UPDATE search_activities SET activity_status = 'deactivated' WHERE search_forum_num=:a; """
                )
                conn.execute(sql_text, a=search_num)

                # add the latest activities for the search
                for activity_line in search_activities:
                    sql_text = sqlalchemy.text(
                        """INSERT INTO search_activities (search_forum_num, activity_type, activity_status,
                        timestamp) values ( :a, :b, :c, :d); """
                    )
                    conn.execute(sql_text, a=search_num, b=activity_line, c='ongoing', d=datetime.now())

                # Define managers of the search
                managers = profile_get_managers(parsed_profile_text)

                logging.info(f'DBG.P.104:Managers: {managers}')

                if managers:
                    try:
                        sql_text = sqlalchemy.text(
                            """INSERT INTO search_attributes (search_forum_num, attribute_name, attribute_value,
                            timestamp) values ( :a, :b, :c, :d); """
                        )
                        conn.execute(sql_text, a=search_num, b='managers', c=str(managers), d=datetime.now())
                    except Exception as e:
                        logging.exception(e)

        """4 DEL UPD from Searches"""
        delete_lines_from_summary_list = []

        for snapshot_line in curr_snapshot_list:
            for searches_line in prev_searches_list:
                if snapshot_line.topic_id == searches_line.topic_id:
                    if (
                        snapshot_line.status != searches_line.status
                        or snapshot_line.title != searches_line.title
                        or snapshot_line.num_of_replies != searches_line.num_of_replies
                    ):
                        delete_lines_from_summary_list.append(snapshot_line)

        if delete_lines_from_summary_list:
            stmt = sqlalchemy.text("""DELETE FROM searches WHERE search_forum_num=:a;""")
            for line in delete_lines_from_summary_list:
                conn.execute(stmt, a=int(line.topic_id))

        """5. UPD added to Searches"""
        searches_full_list = conn.execute(
            """SELECT search_forum_num, parsed_time, status, forum_search_title, search_start_time,
            num_of_replies, family_name, age, id, forum_folder_id FROM searches;"""
        ).fetchall()
        curr_searches_list = []
        for searches_line in searches_full_list:
            search = SearchSummary()
            (
                search.topic_id,
                search.parsed_time,
                search.status,
                search.title,
                search.start_time,
                search.num_of_replies,
                search.name,
                search.age,
                search.id,
                search.folder_id,
            ) = list(searches_line)
            curr_searches_list.append(search)

        new_topics_from_snapshot_list = []

        for snapshot_line in curr_snapshot_list:
            new_search_flag = 1
            for searches_line in curr_searches_list:
                if snapshot_line.topic_id == searches_line.topic_id:
                    new_search_flag = 0
                    break
            if new_search_flag == 1:
                new_topics_from_snapshot_list.append(snapshot_line)
        if new_topics_from_snapshot_list:
            stmt = sqlalchemy.text(
                """INSERT INTO searches (search_forum_num, parsed_time, forum_search_title,
                search_start_time, num_of_replies, age, family_name, forum_folder_id,
                topic_type, display_name, age_min, age_max, status, city_locations, topic_type_id) values
                (:a, :b, :d, :e, :f, :g, :h, :i, :j, :k, :l, :m, :n, :o, :p); """
            )
            for line in new_topics_from_snapshot_list:
                conn.execute(
                    stmt,
                    a=line.topic_id,
                    b=line.parsed_time,
                    d=line.title,
                    e=line.start_time,
                    f=line.num_of_replies,
                    g=line.age,
                    h=line.name,
                    i=line.folder_id,
                    j=line.topic_type,
                    k=line.display_name,
                    l=line.age_min,
                    m=line.age_max,
                    n=line.new_status,
                    o=str(line.locations),
                    p=line.topic_type_id,
                )

        conn.close()

    # DEBUG - function execution time counter
    func_finish = datetime.now()
    func_execution_time_ms = func_finish - func_start
    logging.info(f'DBG.P.5.process_delta() exec time: {func_execution_time_ms}')
    # DEBUG - function execution time counter

    return change_log_ids


def process_one_folder(db, folder_to_parse):
    """process one forum folder: check for updates, upload them into cloud sql"""

    def update_checker(current_hash, folder_num):
        """compare prev snapshot and freshly-parsed snapshot, returns NO or YES and Previous hash"""

        # pre-set default output from the function
        upd_trigger = False

        # read the previous snapshot from Storage and save it as output[1]
        previous_hash = read_snapshot_from_cloud_storage('bucket_for_snapshot_storage', folder_num)

        # if new snapshot differs from the old one – then let's update the old with the new one
        if current_hash != previous_hash:
            # update hash in Storage
            write_snapshot_to_cloud_storage('bucket_for_snapshot_storage', current_hash, folder_num)

            upd_trigger = True

        logging.info(
            f'folder = {folder_num}, update trigger = {upd_trigger}, prev snapshot as string = {previous_hash}'
        )

        return upd_trigger

    def rewrite_snapshot_in_sql(db2, folder_num, folder_summary):
        """rewrite the freshly-parsed snapshot into sql table 'forum_summary_snapshot'"""

        with db2.connect() as conn:
            sql_text = sqlalchemy.text("""DELETE FROM forum_summary_snapshot WHERE forum_folder_id = :a;""")
            conn.execute(sql_text, a=folder_num)

            sql_text = sqlalchemy.text(
                """INSERT INTO forum_summary_snapshot (search_forum_num, parsed_time, forum_search_title,
                search_start_time, num_of_replies, age, family_name, forum_folder_id, topic_type, display_name, age_min,
                age_max, status, city_locations, topic_type_id)
                VALUES (:a, :b, :d, :e, :f, :g, :h, :i, :j, :k, :l, :m, :n, :o, :p); """
            )
            # FIXME – add status
            for line in folder_summary:
                conn.execute(
                    sql_text,
                    a=line.topic_id,
                    b=line.parsed_time,
                    d=line.title,
                    e=line.start_time,
                    f=line.num_of_replies,
                    g=line.age,
                    h=line.name,
                    i=line.folder_id,
                    j=line.topic_type,
                    k=line.display_name,
                    l=line.age_min,
                    m=line.age_max,
                    n=line.new_status,
                    o=str(line.locations),
                    p=line.topic_type_id,
                )
            conn.close()

        return None

    change_log_ids = []

    # parse a new version of summary page from the chosen folder
    titles_and_num_of_replies, new_folder_summary = parse_one_folder(db, folder_to_parse)

    update_trigger = False
    debug_message = f'folder {folder_to_parse} has NO new updates'

    if new_folder_summary:
        # transform the current snapshot into the string to be able to compare it: string vs string
        curr_snapshot_as_one_dimensional_list = [y for x in titles_and_num_of_replies for y in x]
        curr_snapshot_as_string = ','.join(map(str, curr_snapshot_as_one_dimensional_list))

        # get the prev snapshot as string from cloud storage & get the trigger if there are updates at all
        update_trigger = update_checker(curr_snapshot_as_string, folder_to_parse)

        # only for case when current snapshot differs from previous
        if update_trigger:
            debug_message = f'folder {folder_to_parse} HAS an update'

            rewrite_snapshot_in_sql(db, folder_to_parse, new_folder_summary)

            logging.info(f'starting updating change_log and searches tables for folder {folder_to_parse}')

            change_log_ids = update_change_log_and_searches(db, folder_to_parse)
            update_coordinates(db, new_folder_summary)

    logging.info(debug_message)

    return update_trigger, change_log_ids


def get_the_list_of_ignored_folders(db):
    """get the list of folders which does not contain searches – thus should be ignored"""

    conn = db.connect()

    sql_text = sqlalchemy.text(
        """SELECT folder_id FROM geo_folders WHERE folder_type != 'searches' AND folder_type != 'events';"""
    )
    raw_list = conn.execute(sql_text).fetchall()

    list_of_ignored_folders = [int(line[0]) for line in raw_list]

    conn.close()

    return list_of_ignored_folders


def generate_random_function_id():
    """generates a random ID for every function – to track all function dependencies (no built-in ID in GCF)"""

    random_id = random.randint(100000000000, 999999999999)

    return random_id


def save_function_into_register(db, context, start_time, function_id, change_log_ids):
    """save current function into functions_registry"""

    try:
        event_id = context.event_id
        json_of_params = json.dumps({'ch_id': change_log_ids})

        with db.connect() as conn:
            sql_text = sqlalchemy.text("""INSERT INTO functions_registry
                                                      (event_id, time_start, cloud_function_name, function_id,
                                                      time_finish, params)
                                                      VALUES (:a, :b, :c, :d, :e, :f)
                                                      /*action='save_ide_topics_function' */;""")
            conn.execute(
                sql_text,
                a=event_id,
                b=start_time,
                c='identify_updates_of_topics',
                d=function_id,
                e=datetime.now(),
                f=json_of_params,
            )
            logging.info(f'function {function_id} was saved in functions_registry')

    except Exception as e:
        logging.info(f'function {function_id} was NOT ABLE to be saved in functions_registry')
        logging.exception(e)

    return None


def main(event, context):  # noqa
    """main function triggered by pub/sub"""

    global requests_session

    function_id = generate_random_function_id()
    folders_list = []

    analytics_func_start = datetime.now()
    requests_session = requests.Session()

    message_from_pubsub = process_pubsub_message(event)
    list_from_pubsub = ast.literal_eval(message_from_pubsub) if message_from_pubsub else None
    logging.info(f'received message from pub/sub: {message_from_pubsub}')

    db = sql_connect()
    list_of_ignored_folders = get_the_list_of_ignored_folders(db)

    if list_from_pubsub:
        folders_list = [int(line[0]) for line in list_from_pubsub if int(line[0]) not in list_of_ignored_folders]
        logging.info(f'list of folders, received from pubsub but filtered by ignored folders: {folders_list}')

    if not folders_list:
        notify_admin(f'NB! [Ide_topics] resulted in empty folders list. Initial, but filtered {list_from_pubsub}')
        folders_list = [276, 41]

    list_of_folders_with_updates = []
    change_log_ids = []

    if folders_list:
        for folder in folders_list:
            logging.info(f'start checking if folder {folder} has any updates')

            update_trigger, one_folder_change_log_ids = process_one_folder(db, folder)

            if update_trigger:
                list_of_folders_with_updates.append(folder)
                change_log_ids += one_folder_change_log_ids

    logging.info(f"Here's a list of folders with updates: {list_of_folders_with_updates}")
    logging.info(f"Here's a list of change_log ids created: {change_log_ids}")

    if list_of_folders_with_updates:
        save_function_into_register(db, context, analytics_func_start, function_id, change_log_ids)

        message_for_pubsub = {'triggered_by_func_id': function_id, 'text': "let's compose notifications"}
        publish_to_pubsub('topic_for_notification', message_for_pubsub)

    requests_session.close()
    db.dispose()

    return None
