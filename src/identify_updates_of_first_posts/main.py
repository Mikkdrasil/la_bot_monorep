"""Check if the first post of the search was updated in terms of field trips and coordinates change.
Result to be recorded into Change_log and triggered another script identify_updates_of_folders."""

import ast
import base64
import copy
import datetime
import difflib
import json
import logging
import random
import re
import urllib.request

import google.cloud.logging
import requests
import sqlalchemy
from bs4 import BeautifulSoup, NavigableString
from google.cloud import pubsub_v1, secretmanager

url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
req = urllib.request.Request(url)
req.add_header('Metadata-Flavor', 'Google')
project_id = urllib.request.urlopen(req).read().decode()

publisher = pubsub_v1.PublisherClient()
client = secretmanager.SecretManagerServiceClient()

log_client = google.cloud.logging.Client()
log_client.setup_logging()

requests_session = requests.Session()


def get_secrets(secret_request):
    """get GCP secret"""

    name = f'projects/{project_id}/secrets/{secret_request}/versions/latest'
    response = client.access_secret_version(name=name)

    return response.payload.data.decode('UTF-8')


def sql_connect():
    """connect to PSQL in GCP"""

    db_user = get_secrets('cloud-postgres-username')
    db_pass = get_secrets('cloud-postgres-password')
    db_name = get_secrets('cloud-postgres-db-name')
    db_conn = get_secrets('cloud-postgres-connection-name')
    db_socket_dir = '/cloudsql'

    db_config = {
        'pool_size': 5,
        'max_overflow': 0,
        'pool_timeout': 0,  # seconds
        'pool_recycle': 30,  # seconds
    }

    pool = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL(
            'postgresql+pg8000',
            username=db_user,
            password=db_pass,
            database=db_name,
            query={'unix_sock': f'{db_socket_dir}/{db_conn}/.s.PGSQL.5432'},
        ),
        **db_config,
    )
    pool.dialect.description_encoding = None

    return pool


def process_pubsub_message(event):
    """get the readable message from incoming pub/sub call"""

    # receive message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
    encoded_to_ascii = eval(received_message_from_pubsub)
    data_in_ascii = encoded_to_ascii['data']
    message_in_ascii = str(data_in_ascii['message'])

    logging.info(f'LOGGING-INFO: incoming Pub/Sub message: {message_in_ascii}')

    return message_in_ascii


def publish_to_pubsub(topic_name, message):
    """publish a new message to pub/sub"""

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
        logging.error('Not able to send pub/sub message')
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


def get_the_list_of_coords_out_of_text(initial_text):
    """get all the pairs of coordinates in the given text"""

    list_of_all_coord_mentions = []
    resulting_list = []

    if initial_text:
        # remove blank spaces and newlines in the initial text
        initial_text = initial_text.replace('<br>', ' ')
        initial_text = initial_text.replace('\n', ' ')

        # get the list of all mentions of coords at all
        # majority of coords in RU: lat in [40-80], long in [20-180], expected minimal format = XX.X
        list_of_all_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', initial_text)
        if list_of_all_coords:
            for line in list_of_all_coords:
                nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line)
                list_of_all_coord_mentions.append([float(nums[0]), float(nums[1]), '2. coordinates w/o word coord'])

        # get the list of all mentions with word 'Coordinates'
        list_of_all_mentions_of_word_coord = re.findall(r'[Кк]оординат[^ор].{0,150}', initial_text)
        if list_of_all_mentions_of_word_coord:
            for line in list_of_all_mentions_of_word_coord:
                list_of_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '1. coordinates w/ word coord'

        # get the deleted coordinates
        soup = BeautifulSoup(initial_text, features='html.parser')
        deleted_text = soup.find_all('span', {'style': 'text-decoration:line-through'})
        if deleted_text:
            for line in deleted_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '3. deleted coord'

        # TODO: can be simplified by removing duplication with deleted coords
        # get the boxed coordinates (like in https://lizaalert.org/forum/viewtopic.php?f=276&t=54417 )
        boxed_text = soup.find_all('dl', {'class': 'codebox'})
        if boxed_text:
            for line in boxed_text:
                line = str(line)
                list_of_coords = re.findall(r'0?[3-8]\d\.\d{1,10}.{0,10}(?:0,1)?[2-8]\d\.\d{1,10}', line)
                if list_of_coords:
                    for line_2 in list_of_coords:
                        nums = re.findall(r'0?[2-8]\d\.\d{1,10}', line_2)
                        for line_3 in list_of_all_coord_mentions:
                            if float(nums[0]) == line_3[0] and float(nums[1]) == line_3[1]:
                                line_3[2] = '5. boxed coord'

        # remove duplicates
        if list_of_all_coord_mentions:
            for line in list_of_all_coord_mentions:
                if line not in resulting_list:
                    resulting_list.append(line)

    # output [[lat_1, lon_1, type_1], ... ,[lat_N, lon_N, type_N]]
    return resulting_list


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

    def delete_sorted_out_one_tag(content, tag):
        # language=regexp
        patterns = [
            [r'(?i)Всем выезжающим иметь СИЗ', 'sort_out'],
            # INFO SUPPORT
            [r'(?i)ТРЕБУЕТСЯ ПОМОЩЬ В РАСПРОСТРАНЕНИИ ИНФОРМАЦИИ ПО СЕТИ', 'sort_out'],
            [r'(?i)Задача на поиске,? с которой может помочь каждый', 'sort_out'],
            [r'(?i)Помочь может каждый из вас', 'sort_out'],
            [r'(?i)таблица прозвона', 'sort_out'],
            # PERSON – REASON
            [r'(?i)(местонахождение неизвестно|не выходит на связь)', 'sort_out'],
            [r'(?i)[^\n]{0,1000}(вы|у)ш(ла|[её]л).{1,200}не вернул(ся|ась)', 'sort_out'],
            [r'(?i)(пропал[аи]? во время|не вернул(ся|[аи]сь) с) прогулки', 'sort_out'],
            [r'не дошел до школы', 'sort_out'],
            [r'уш(ёл|ел|ла|ли) (из дома )?в неизвестном направлении', 'sort_out'],
            [
                r'(вы|у)ш(ёл|ел|ла|ли) (из дома )?(и пропал[аи]?|и не вернул(ся|ась)|в неизвестном направлении)',
                'sort_out',
            ],
            [r'уш(ёл|ел|ла|ли) из медицинского учреждения', 'sort_out'],
            # PERSON – DETAILS
            [r'(?i)МОЖЕТ НАХОДИТЬСЯ В ВАШЕМ (РАЙОНЕ|городе)', 'sort_out'],
            [r'(?i)((НУЖДАЕТСЯ|МОЖЕТ НУЖДАТЬСЯ) В МЕДИЦИНСКОЙ ПОМОЩИ|Отставание в развити|потеря памяти)', 'sort_out'],
            [
                r'(?i)(приметы|был[аи]? одет[аы]?|рост\W|телосложени|цвет глаз|'
                r'(^|\W)(куртка|шапка|сумка|волосы|глаза)($|\W))',
                'sort_out',
            ],
            [r'(?i)(^|\W)оджеда(?!.{1,3}(лес|город))', 'sort_out'],
            # GENERAL PHRASES
            [r'(?i)С признаками ОРВИ оставайтесь дома', 'sort_out'],
            [r'(?i)Берегите себя и своих близких', 'sort_out'],
            [r'(?i)ориентировка на ', 'sort_out'],
            [r'(?i)(^|\n)[-_]{2,}(\n|$)', 'sort_out'],
            [r'(?i)подпишитесь на бесплатную SMS-рассыл', 'sort_out'],
            [r'(?i)выражаем .{0,20}благодарность за', 'sort_out'],
            [r'(?i)Все фото/видео с поиска просьба отправлять', 'sort_out'],
            [r'(?i)Предоставлять комментарии по поиску для СМИ могут только', 'sort_out'],
            [r'Если же представитель СМИ хочет', 'sort_out'],
            [r'8\(800\)700-?54-?52', 'sort_out'],
            [r'smi@lizaalert.org', 'sort_out'],
            [r'https://la-org.ru/images/', 'sort_out'],
            [r'(?i)Запрос на согласование фото- и видеосъемки', 'sort_out'],
            [r'(?i)тема в соц сетях', 'sort_out'],
            [r'(?i)Всё, что нужно знать, собираясь на свой первый поиск', 'sort_out'],
            [r'(?i)тема в вк', 'sort_out'],
            [r'(?i)Следите за темой', 'sort_out'],
            [r'(?i)внимание!$', 'sort_out'],
            [r'(?i)Огромная благодарность всем кто откликнулся', 'sort_out'],
            [r'(?i)Канал оповещения об активных выездах и автономных задачах', 'sort_out'],
            [r'(?i)Как стать добровольцем отряда «ЛизаАлерт»?', 'sort_out'],
            [r'(?i)Уважаемые заявители', 'sort_out'],
            [r'(?i)привет.{1,4}Я mikhel', 'sort_out'],
            [r'(?i)Новичковая отряда', 'sort_out'],
            [r'(?i)Горячая линия', 'sort_out'],
            [r'(?i)Анкета добровольца', 'sort_out'],
            [r'(?i)Бесплатная SMS-рассылка', 'sort_out'],
            [r'(?i)Рассылка Вконтакте', 'sort_out'],
            [r'(?i)Телеграм-канал ПСО', 'sort_out'],
            [r'(?i)Рекомендуемый список оборудования', 'sort_out'],
            # MANAGERS
            [r'(?i)(инфорги?( поиска| выезда)?:|снм\W|^ОД\W|^ДИ\W|Старш(ая|ий) на месте)', 'sort_out'],
            [r'(?i)Коорд(инатор)?([-\s]консультант)?(?!инат)', 'sort_out'],
            [r'(?i)написать .{0,50}в (телеграм|telegram)', 'sort_out'],
            [r'(?i)Лимура \(Наталья\)', 'sort_out'],
            [r'(?i)Тутси \(Светлана\)', 'sort_out'],
            [r'(?i)(Герда Ольга|Ольга Герда)', 'sort_out'],
            [r'(?i)Ксен \( ?Ксения\)', 'sort_out'],
            [r'(?i)Сплин \(Наталья\)', 'sort_out'],
            [r'(?i)Марва Валерия', 'sort_out'],
            [r'(?i)Валькирия \(Лилия\)', 'sort_out'],
            [r'(?i)Старовер \( ?Александр\)', 'sort_out'],
            [r'(?i)Верба \(Ольга\)', 'sort_out'],
            [r'(?i)Миледи Елена', 'sort_out'],
            [r'(?i)Красикова Людмила', 'sort_out'],
            [r'(?i)написать .{0,25}в Тг', 'sort_out'],
            [r'(?i)Мария \(Марёна\)', 'sort_out'],
            [r'(?i)Михалыч \(Александр\)', 'sort_out'],
            [r'(?i)https://telegram.im/@buklya_LA71', 'sort_out'],
            [r'(?i)Наталья \(Чента\)', 'sort_out'],
            [r'(?i)Ирина \(Кеттари\)', 'sort_out'],
            [r'(?i)Юлия \(Тайга\)', 'sort_out'],
            [r'(?i)Ольга \(Весна\)', 'sort_out'],
            [r'(?i)Селена \(Элина\)', 'sort_out'],
            [r'(?i)Гроттер \(Татьяна\)', 'sort_out'],
            [r'(?i)БарбиЕ \(Елена\)', 'sort_out'],
            [r'(?i)Элька', 'sort_out'],
            [r'(?i)Иван \(Кел\)', 'sort_out'],
            [r'(?i)Анна \(Эстер\)', 'sort_out'],
            [r'(?i)Википедия \(Ирина\)', 'sort_out'],
            [r'(?i)Миледи \(Елена\)', 'sort_out'],
            [r'(?i)Сплин Наталья', 'sort_out'],
            [r'(?i)Doc\.Vatson \(Анастасия\)', 'sort_out'],
            [r'(?i)Юля Онега', 'sort_out'],
            [r'(?i)Андрей Хрящик', 'sort_out'],
            [r'(?i)Юрий \(Бер\)', 'sort_out'],
            [r'(?i)Птаха Ольга', 'sort_out'],
            [r'(?i)Наталья Шелковица', 'sort_out'],
            [r'(?i)Булка \(Анастасия\)', 'sort_out'],
            [r'(?i)Палех \(Алексей\)', 'sort_out'],
            [r'(?i)Wikipedia57 Ирина', 'sort_out'],
            [r'(?i)Аврора Анастасия', 'sort_out'],
            [r'(?i)Анастасия Булка', 'sort_out'],
            [r'(?i)Александр \(Кузьмич\)', 'sort_out'],
            [r'(?i)Ирина Айриш', 'sort_out'],
            [r'(?i)Киви Ирина', 'sort_out'],
            [r'(?i)Матрона \(Екатерина\)', 'sort_out'],
            [r'(?i)Сергей \(Синий\)', 'sort_out'],
            [r'(?i)Татьяна \(Ночка\)', 'sort_out'],
            [r'(?i)Сара \(Анна\)', 'sort_out'],
            [r'(?i)Наталья \(Марта\)', 'sort_out'],
            [r'(?i)Ксения "Ята"', 'sort_out'],
            [r'(?i)Катерина \(Бусинка\)', 'sort_out'],
            [r'(?i)Ирина \(Динка\)', 'sort_out'],
            [r'(?i)Яна \(Янка\)', 'sort_out'],
            [r'(?i)Катя Кошка', 'sort_out'],
            [r'(?i)Владимир1974', 'sort_out'],
            [r'(?i)Екатерина \(Феникс\)', 'sort_out'],
            [r'(?i)Алёна \(Тайга\)', 'sort_out'],
            [r'(?i)Ашка Екатерина', 'sort_out'],
            [r'(?i)Пёрышко Надежда', 'sort_out'],
            [r'(?i)Анна Ваниль', 'sort_out'],
            [r'(?i)Космос \(Алексей\)', 'sort_out'],
            [r'(?i)Слон \(Артем\)', 'sort_out'],
            [r'(?i)Мотя \(Алина\)', 'sort_out'],
            [r'(?i)Екатерина Кирейчик', 'sort_out'],
            [r'(?i)Леонид Енот', 'sort_out'],
            [r'(?i)Сергей Сом', 'sort_out'],
            [r'(?i)Лиса Елизаветта', 'sort_out'],
            [r'(?i)Ирина "Ластик"', 'sort_out'],
            [r'(?i)Светлана "Клюква"', 'sort_out'],
            [r'(?i)Сара \(Анна\)', 'sort_out'],
            [r'(?i)Наталья \(Марта\)', 'sort_out'],
            [r'(?i)Ольга Елка', 'sort_out'],
            [r'(?i)Ксен \(Ксения\)', 'sort_out'],
            [r'(?i)Огонек \(Алена\)', 'sort_out'],
            [r'(?i)Бро Елена', 'sort_out'],
            [r'(?i)Добрая фея Настя', 'sort_out'],
            [r'(?i)Лимура Наталья', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
            # EXCEPTIONS
            [r'(?i)автономн.{2,4} округ', 'sort_out'],
            [r'(?i)ид[ёе]т сбор информации', 'sort_out'],
            [r'(?i)телефон неактивен', 'sort_out'],
            [r'(?i)проявля.{1,4} активность', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
            [r'(?i)XXX', 'sort_out'],
        ]

        if not tag:
            return content

        for pattern in patterns:
            if isinstance(tag, NavigableString) and re.search(pattern[0], tag):
                tag.extract()
            elif not isinstance(tag, NavigableString) and re.search(pattern[0], tag.text):
                tag.decompose()

        if not isinstance(tag, NavigableString):
            if (
                tag.name == 'span'
                and tag.attrs
                in [
                    {'style': 'font-size:140%;line-height:116%'},
                    {'style': 'font-size: 140%;line-height:116%'},
                    {'style': 'font-size: 140%;line-height: 116%'},
                ]
                or tag.name == 'img'
            ):
                tag.decompose()

        return content

    def delete_sorted_out_all_tags(content):
        elements = content.body
        for tag in elements:
            content = delete_sorted_out_one_tag(content, tag)

        return content

    if not init_content or re.search(r'Для просмотра этого форума вы должны быть авторизованы', init_content):
        return None

    reco_content = cook_soup(init_content)
    reco_content = prettify_soup(reco_content)
    reco_content = remove_links(reco_content)
    reco_content = delete_sorted_out_all_tags(reco_content)

    # reco_content = reco_content.prettify()
    reco_content = reco_content.text
    reco_content = re.sub(r'\n{2,}', '\n', reco_content)

    if not re.search(r'\w', reco_content):
        return None

    reco_content = reco_content.split('\n')

    # language=regexp
    patterns = [
        r'(\[/?[biu]]|\[/?color.{0,8}]|\[/?quote]|\[/?size.{0,8}]|\[/?spoiler=?]?)',
        r'(?i)последний раз редактировалось.{1,200}',
        r'(?i).{1,200}\d\d:\d\d, всего редактировалось.{1,200}',
        r'^\s+',
    ]

    for pattern in patterns:
        reco_content = [re.sub(pattern, '', line) for line in reco_content]

    reco_content = [re.sub('ё', 'е', line) for line in reco_content]

    translate_table = str.maketrans({'{': r'\{', '}': r'\}'})
    reco_content = [line.translate(translate_table) for line in reco_content]

    return reco_content


def compose_diff_message(curr_list, prev_list):
    message = ''

    if not curr_list or not prev_list:
        return message, [], []

    diff = difflib.unified_diff(prev_list, curr_list, lineterm='')

    list_of_deletions = []
    list_of_additions = []

    for line in diff:
        if line[0] == '-':
            addition = re.sub(r'^[\s+-]+', '', line)
            if addition:
                list_of_deletions.append(addition)
        elif line[0] == '+':
            addition = re.sub(r'^[\s+-]+', '', line)
            if addition:
                list_of_additions.append(addition)

    if list_of_deletions:
        message += 'Удалено:\n<s>'
        for line in list_of_deletions:
            message += f'{line}\n'
        message += '</s>'

    if list_of_additions:
        if message:
            message += '\n'
        message += 'Добавлено:\n'
        for line in list_of_additions:
            # majority of coords in RU: lat in [30-80], long in [20-180]
            updated_line = re.sub(r'0?[3-8]\d\.\d{1,10}.{0,3}([2-9]\d|1\d{2})\.\d{1,10}', r'<code>\g<0></code>', line)
            message += f'{updated_line}\n'

    return message, list_of_deletions, list_of_additions


def process_first_page_comparison(conn, search_id, first_page_content_prev, first_page_content_curr):
    """compare first post content to identify any diffs"""

    # check the latest status on this search
    sql_text = sqlalchemy.text("""SELECT display_name, status, family_name, age, status
                                      FROM searches WHERE search_forum_num=:a;""")

    what_is_saved_in_psql = conn.execute(sql_text, a=search_id).fetchone()

    if not what_is_saved_in_psql:
        logging.info('first page comparison failed – nothing is searches psql table')
        return None, None

    try:
        # FIXME – just to double-check
        print(f' we print that what_is_saved_in_psql = {what_is_saved_in_psql}')
        print(f' we print "not what_is_saved_in_psql" = {not what_is_saved_in_psql}')
        print(f' we print "what_is_saved_in_psql == None" = {what_is_saved_in_psql is None}')
        print(f' we print "what_is_saved_in_psql == Null" = {what_is_saved_in_psql == "Null"}')
        # FIXME ^^^

        display_name, status, name, age, status_old = list(what_is_saved_in_psql)
    except Exception as e:
        notify_admin('this strange exception happened, check [ide_posts]')
        logging.exception(e)
        return None, None

    # updates are made only for non-finished searches
    if status != 'Ищем':
        return None, None

    prev_clean_content = clean_up_content(first_page_content_prev)
    curr_clean_content = clean_up_content(first_page_content_curr)

    message, list_of_del, list_of_add = compose_diff_message(curr_clean_content, prev_clean_content)

    # case when there is only 1 line changed and the change is in one blank space or letter – we don't notify abt it
    if list_of_del and list_of_add and len(list_of_del) == 1 and len(list_of_add) == 1:
        diff = difflib.ndiff(list_of_del[0], list_of_add[0])
        changes = ''
        for line in diff:
            if line[0] in {'-', '+'}:
                changes += line[1:]
        changes = re.sub(r'\s', '', changes)  # changes in blank lines are irrelevant
        changes = re.sub(r'\D', '', changes, count=1)  # changes for only one letter – irrelevant (but not for digit)
        if not changes:
            try:
                notify_admin(
                    f'[ide_posts]: IGNORED MINOR CHANGE: \ninit message: {message}'
                    f'\ndel: {list_of_del}\nadd: {list_of_add}'
                )
            except:  # noqa
                notify_admin('THIS ERROR')
            return '', None

    message_dict = {'del': list_of_del, 'add': list_of_add, 'message': message}

    return message, message_dict


def save_new_record_into_change_log(conn, search_id, coords_change_list, changed_field, change_type):
    """save the coordinates change into change_log"""

    stmt = sqlalchemy.text(
        """INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, change_type)
        values (:a, :b, :c, :d, :e) RETURNING id;"""
    )

    raw_data = conn.execute(
        stmt, a=datetime.datetime.now(), b=search_id, c=changed_field, d=str(coords_change_list), e=change_type
    ).fetchone()
    change_log_id = raw_data[0]

    return change_log_id


def parse_search_folder(search_num):
    """parse search's folder number"""

    folder = None

    url = 'https://lizaalert.org/forum/viewtopic.php?t=' + str(search_num)
    r = requests_session.get(url)  # 10 seconds – do we need it in this script?
    content = r.content.decode('utf-8')

    soup = BeautifulSoup(content, features='html.parser')
    spans = soup.find_all('span', {'class': 'crumb'})

    for line in spans:
        try:
            folder = int(line['data-forum-id'])
        except:  # noqa
            pass

    return folder


def get_compressed_first_post(initial_text):
    """convert the initial html text of first post into readable string (for reading in SQL)"""

    compressed_string = ''

    if initial_text:
        text_to_soup = BeautifulSoup(initial_text, features='html.parser')

        basic_text_string = text_to_soup.text
        basic_text_string = basic_text_string.replace('\n', ' ')

        # width of text block in symbols
        block_width = 50

        list_from_string = [
            basic_text_string[i : i + block_width] for i in range(0, len(basic_text_string), block_width)
        ]

        for list_line in list_from_string:
            compressed_string += list_line + '\n'

    return compressed_string


def split_text_to_deleted_and_regular_parts(text):
    """split text into two strings: one for deleted (line-through) text and second for regular"""

    soup = BeautifulSoup(text, features='html.parser')

    soup_without_deleted = copy.copy(soup)
    deleted_text = soup_without_deleted.find_all('span', {'style': 'text-decoration:line-through'})
    for case in deleted_text:
        case.decompose()
    non_deleted_text = str(soup_without_deleted)

    deleted_list = [
        item.getText(strip=False) for item in soup.find_all('span', {'style': 'text-decoration:line-through'})
    ]

    deleted_text = '\n'.join(deleted_list)

    # TODO: debug
    print(f'deleted text = {deleted_text}')
    print(f'non-deleted text = {non_deleted_text}')
    # TODO: debug

    return deleted_text, non_deleted_text


def get_field_trip_details_from_text(text):
    """return the dict with 'filed trip' parameters for the search's text"""

    """resulting_field_trip_dict = {'vyezd': False,  # True for vyezd
                                     'sbor': False,  # True for sbor

                                     'now': True,  # True for now of and False for future
                                     'urgent': False,  # True for urgent
                                     'secondary': False,  # True for secondary

                                     'coords': None,  # [lat, lon] for the most relevant pair of coords

                                     'date_and_time': None,  # time of filed trip
                                     'address': None,  # place of filed trip (not coords)
                                     }"""

    class FieldTrip:
        def __init__(
            self,
            field_trip=False,
            camp=False,
            now=False,
            urgent=False,
            repeat=False,
            coordinates=None,
            date_and_time=None,
            place=None,
            blocks=None,
        ):
            coordinates = []
            blocks = []
            self.trip = field_trip
            self.camp = camp
            self.now = now
            self.urgent = urgent
            self.repeat = repeat
            self.coords = coordinates
            self.time = date_and_time
            self.place = place
            self.b = blocks

    class Block:
        def __init__(self, type=None, title=None, time=None, place=None, coords=None):
            self.type = type
            self.title = title
            self.time = time
            self.place = place
            self.coords = coords

    field_trip_vyezd = re.findall(
        r'(?i)(?:внимание.{0,3}|)'
        r'(?:скоро.{0,3}|срочно.{0,3}|)'
        r'(?:планируется.{0,3}|ожидается.{0,3}|готовится.{0,3}|запланирован.{0,3}|)'
        r'(?:повторный.{0,3}|срочный.{0,3}|активный.{0,3})?'
        r'(?:выезд|вылет|cбор на поиск|сбор)'
        r'(?:.{0,3}срочно|сейчас|)'
        r'(?:.{0,3}планируется|.{0,3}ожидается|.{0,3}готовится|.{0,3}запланирован|)'
        r'(?:.{0,4}\d\d\.\d\d\.\d\d(?:\d\d|)|)'
        r'.{0,3}(?:[\r\n]+|.){0,1000}',
        text,
    )

    # TODO: to be deleted
    field_trip_sbor = re.findall(
        r'(?:место.{0,3}|время.{0,3}|координаты.{0,3}(?:места.{0,3}|)|)сбор(?:а|)', text.lower()
    )
    # TODO: to be deleted

    resulting_field_trip_dict = {'vyezd': False}

    trip = FieldTrip()

    # Update the parameters of the output_dict
    # vyezd
    if field_trip_vyezd:
        resulting_field_trip_dict['vyezd'] = True
        trip.trip = True

    # TODO: to delete
    # sbor
    if field_trip_sbor:
        resulting_field_trip_dict['sbor'] = True
        trip.camp = True

    # now / urgent / secondary
    for phrase in field_trip_vyezd:
        # now
        if re.findall(r'(планируется|ожидается|готовится)', phrase.lower()):
            resulting_field_trip_dict['now'] = False
            resulting_field_trip_dict['planned'] = True

        # urgent
        if re.findall(r'срочн', phrase.lower()):
            resulting_field_trip_dict['urgent'] = True

        # secondary
        if re.findall(r'повторн', phrase.lower()):
            resulting_field_trip_dict['secondary'] = True

    # coords
    coords_curr_full_list = get_the_list_of_coords_out_of_text(text)
    # format [[lat_1, lon_1, type_1], ... ,[lat_N, lon_N, type_N]]

    # TODO: temp debug
    print(f'BBB: coords_curr_full_list={coords_curr_full_list}')
    # TODO: temp debug

    # we just need to get curr coords of type 1 or 2 (with world coords or without)
    lat, lon = None, None
    if coords_curr_full_list:
        for line in coords_curr_full_list:
            if line[2][0] == '1':
                lat, lon = line[0], line[1]

                break
        if lat is None and lon is None:
            for line in coords_curr_full_list:
                if line[2][0] == '2':
                    lat, lon = line[0], line[1]
                    break

    # TODO: temp debug
    print(f'BBB: lat, lon={lat}, {lon}')
    # TODO: temp debug

    if lat is not None and lon is not None:
        resulting_field_trip_dict['coords'] = [lat, lon]

    # date_and_time and address
    for line_ft in field_trip_vyezd:
        list_of_lines = line_ft.splitlines()
        for list_line in list_of_lines:
            r = re.search(r'(?i)(?:^штаб[^а][^\sсвернут]|.{0,10}(?:адрес|место|точка сбора)).{0,100}', list_line)
            if r:
                resulting_field_trip_dict['address'] = re.sub(re.compile('<.*?>'), '', r.group())

            r = re.search(
                r'(?i)^(?!.*мест. сбор).{0,10}(?:время|сбор.{1,3}(?:в\s|к\s|с\s|.{1,10}\d{2}.{1,3}\d{2})).{0,100}',
                list_line,
            )
            if r:
                resulting_field_trip_dict['date_and_time'] = re.sub(re.compile('<.*?>'), '', r.group())

    return resulting_field_trip_dict


def age_writer(age):
    """compose an age string with the right form of years in Russian"""

    if age:
        a = age // 100
        b = (age - a * 100) // 10
        c = age - a * 100 - b * 10
        if c == 1 and b != 1:
            wording = str(age) + ' год'
        elif c in {2, 3, 4} and b != 1:
            wording = str(age) + ' года'
        else:
            wording = str(age) + ' лет'
    else:
        wording = ''

    return wording


def generate_random_function_id():
    """generates a random ID for every function – to track all function dependencies (no built-in ID in GCF)"""

    random_id = random.randint(100000000000, 999999999999)

    return random_id


def save_function_into_register(conn, context, start_time, function_id, change_log_ids):
    """save current function into functions_registry"""

    try:
        event_id = context.event_id
        json_of_params = json.dumps({'ch_id': change_log_ids})

        sql_text = sqlalchemy.text("""INSERT INTO functions_registry
                                                  (event_id, time_start, cloud_function_name, function_id,
                                                  time_finish, params)
                                                  VALUES (:a, :b, :c, :d, :e, :f)
                                                  /*action='save_ide_f_posts_function' */;""")
        conn.execute(
            sql_text,
            a=event_id,
            b=start_time,
            c='identify_updates_of_f_posts',
            d=function_id,
            e=datetime.datetime.now(),
            f=json_of_params,
        )
        logging.info(f'function {function_id} was saved in functions_registry')

    except Exception as e:
        logging.info(f'function {function_id} was NOT ABLE to be saved in functions_registry')
        logging.exception(e)

    return None


def main(event, context):  # noqa
    """key function"""

    function_id = generate_random_function_id()
    analytics_func_start = datetime.datetime.now()

    # receive a list of searches where first post was updated
    message_from_pubsub = process_pubsub_message(event)
    list_of_updated_searches = ast.literal_eval(message_from_pubsub)

    change_log_ids = []

    if list_of_updated_searches:
        pool = sql_connect()
        with pool.connect() as conn:
            try:
                list_of_folders_with_upd_searches = []

                for search_id in list_of_updated_searches:
                    # get the Current First Page Content
                    sql_text = sqlalchemy.text("""
                    SELECT content, content_compact FROM search_first_posts WHERE search_id=:a AND actual = True;
                    """)
                    raw_data = conn.execute(sql_text, a=search_id).fetchone()
                    first_page_content_curr = raw_data[0]
                    first_page_content_curr_compact = raw_data[1]

                    # TODO: why we're doing it in this script but not in che_posts??
                    # save compact first page content
                    if not first_page_content_curr_compact:
                        content_compact = get_compressed_first_post(first_page_content_curr)
                        sql_text = sqlalchemy.text("""
                                        UPDATE search_first_posts SET content_compact=:a
                                        WHERE search_id=:b AND actual = True;
                                        """)
                        conn.execute(sql_text, a=content_compact, b=search_id)

                    # get the Previous First Page Content
                    sql_text = sqlalchemy.text("""
                                   SELECT content
                                   FROM search_first_posts
                                   WHERE search_id=:a AND actual=False
                                   ORDER BY timestamp DESC;
                                   """)
                    first_page_content_prev = conn.execute(sql_text, a=search_id).fetchone()[0]

                    logging.info(f'topic id {search_id} has an update of first post:')
                    logging.info(f'first page content prev: {first_page_content_prev}')
                    logging.info(f'first page content curr: {first_page_content_curr}')

                    # TODO: DEBUG try
                    try:
                        if first_page_content_curr and first_page_content_prev:
                            # check the difference b/w first posts for current and previous version
                            message_on_first_posts_diff, diff_dict = process_first_page_comparison(
                                conn, search_id, first_page_content_prev, first_page_content_curr
                            )
                            if message_on_first_posts_diff:
                                message_on_first_posts_diff = str(diff_dict)
                                change_log_id = save_new_record_into_change_log(
                                    conn, search_id, message_on_first_posts_diff, 'topic_first_post_change', 8
                                )
                                change_log_ids.append(change_log_id)

                    except Exception as e:
                        logging.info('[ide_posts]: Error fired during output_dict creation.')
                        logging.exception(e)
                        notify_admin('[ide_posts]: Error fired during output_dict creation.')

                    # save folder number for the search that has an update
                    folder_num = parse_search_folder(search_id)
                    new_line = [folder_num, None] if folder_num else None

                    if new_line and new_line not in list_of_folders_with_upd_searches:
                        list_of_folders_with_upd_searches.append(new_line)

                # evoke 'parsing script' to check if the folders with updated searches have any update
                if list_of_folders_with_upd_searches:
                    # notify_admin(f'[ide_post]: {str(list_of_folders_with_upd_searches)}')

                    save_function_into_register(conn, context, analytics_func_start, function_id, change_log_ids)

                    publish_to_pubsub('topic_to_run_parsing_script', str(list_of_folders_with_upd_searches))
                    message_for_pubsub = {
                        'triggered_by_func_id': function_id,
                        'text': str(list_of_folders_with_upd_searches),
                    }
                    publish_to_pubsub('topic_for_notification', message_for_pubsub)

            except Exception as e:
                logging.info('exception in main function')
                logging.exception(e)

            conn.close()
        pool.dispose()
    requests_session.close()

    return 'ok'
