import asyncio
import base64
import datetime
import logging
import re
import urllib.parse
import urllib.request
from time import sleep

import google.cloud.logging
import psycopg2
import requests
from bs4 import BeautifulSoup
from google.cloud import secretmanager
from telegram import Bot, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes

url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
req = urllib.request.Request(url)
req.add_header('Metadata-Flavor', 'Google')
project_id = urllib.request.urlopen(req).read().decode()

client = secretmanager.SecretManagerServiceClient()
session = requests.Session()
cur = None
conn_psy = None

log_client = google.cloud.logging.Client()
log_client.setup_logging()


class ForumUser:
    def __init__(
        self,
        user_id=None,
        username=None,
        callsign=None,
        region=None,
        phone=None,
        auto_num=None,
        age=None,
        sex=None,
        reg_date=None,
        firstname=None,
        lastname=None,
    ):
        self.user_id = user_id
        self.username = username
        self.callsign = callsign
        self.region = region
        self.phone = phone
        self.auto_num = auto_num
        self.age = age
        self.sex = sex
        self.reg_date = reg_date
        self.firstname = firstname
        self.lastname = lastname

    def __str__(self):
        return str(
            [
                self.user_id,
                self.username,
                self.firstname,
                self.lastname,
                self.callsign,
                self.region,
                self.phone,
                self.auto_num,
                self.age,
                self.sex,
                self.reg_date,
            ]
        )


def get_secrets(secret_request):
    name = f'projects/{project_id}/secrets/{secret_request}/versions/latest'
    response = client.access_secret_version(name=name)
    return response.payload.data.decode('UTF-8')


def sql_connect_by_psycopg2():
    global cur
    global conn_psy

    db_user = get_secrets('cloud-postgres-username')
    db_pass = get_secrets('cloud-postgres-password')
    db_name = get_secrets('cloud-postgres-db-name')
    db_conn = get_secrets('cloud-postgres-connection-name')
    db_host = '/cloudsql/' + db_conn

    conn_psy = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_pass)
    cur = conn_psy.cursor()


async def send_message_async(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=context.job.chat_id, **context.job.data)

    return None


async def prepare_message_for_async(user_id, data):
    bot_token = get_secrets('bot_api_token__prod')
    application = Application.builder().token(bot_token).build()
    job_queue = application.job_queue
    job_queue.run_once(send_message_async, 0, data=data, chat_id=user_id)

    async with application:
        await application.initialize()
        await application.start()
        await application.stop()
        await application.shutdown()

    return 'ok'


def process_sending_message_async(user_id, data) -> None:
    asyncio.run(prepare_message_for_async(user_id, data))

    return None


def login_into_forum(forum_bot_password):
    """login in into the forum"""

    global session

    login_page = 'https://lizaalert.org/forum/ucp.php?mode=login'
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {'username': 'telegram_bot', 'password': forum_bot_password, 'login': 'Вход'}

    response = session.get(login_page)

    content = response.content.decode('utf-8')

    creation_time_match = re.compile(r'<input.*?name="creation_time".*?value="([^"]*)".*?/>').search(content)
    if creation_time_match:
        data.update({'creation_time': creation_time_match.group(1)})

    redirect_match = re.compile(r'<input.*?name="redirect".*?value="([^"]*)".*?/>').search(content)
    if redirect_match:
        data.update({'redirect': redirect_match.group(1)})

    sid_match = re.compile(r'<input.*?name="sid".*?value="([^"]*)".*?/>').search(content)
    if sid_match:
        data.update({'sid': sid_match.group(1)})

    form_token_match = re.compile(r'<input.*?name="form_token".*?value="([^"]*)".*?/>').search(content)
    if form_token_match:
        data.update({'form_token': form_token_match.group(1)})

    form_data = urllib.parse.urlencode(data)

    sleep(1)  # без этого не сработает %)
    r = session.post(login_page, headers=headers, data=form_data)

    if 'Личные сообщения' in r.text:
        print('Logged in successfully')
    # elif "Ошибка отправки формы" in r.text:
    #    print("Form submit error")
    else:
        print('Login Failed')

    return None


def get_user_id(u_name):
    """get user_id from forum"""

    user_id = 0
    forum_prefix = 'https://lizaalert.org/forum/memberlist.php?username='
    user_search_page = forum_prefix + u_name

    r2 = session.get(user_search_page)
    soup = BeautifulSoup(r2.content, features='html.parser')

    try:
        block_with_username = soup.find('a', {'class': 'username'})
        if block_with_username is None:
            block_with_username = soup.find('a', {'class': 'username-coloured'})

        if block_with_username is not None:
            u_string = str(block_with_username)
            user_id = u_string[u_string.find(';u=') + 3 : u_string.find('">')]
            if user_id.find('style="color:') != -1:
                user_id = user_id[: (user_id.find('style="color:') - 2)]
            print('User found, user_id=', user_id)
        else:
            user_id = 0
            print('User not found')

    except Exception as e:
        print('User not found, exception:', repr(e))
        user_id = 0

    return user_id


def get_user_attributes(user_id):
    """get user data from forum"""

    url_prefix = 'https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
    r3 = session.get(url_prefix + user_id)
    soup = BeautifulSoup(r3.content, features='html.parser')
    block_with_user_attr = soup.find('div', {'class': 'page-body'})

    return block_with_user_attr


def get_user_data(data):
    """aggregates User Profile from forums' data"""

    global user

    dict = {
        'age': 'Возраст:',
        'sex': 'Пол:',
        'region': 'Регион:',
        'phone': 'Мобильный телефон:',
        'reg_date': 'Зарегистрирован:',
        'callsign': 'Позывной:',
    }

    for attr in dict:
        try:
            value = data.find('dt', text=dict[attr]).findNext('dd').text
            setattr(user, attr, value)
        except Exception as e1:
            print(attr, 'is not defined')
            logging.info(e1)

    return None


def match_user_region_from_forum_to_bot(forum_region):
    region_dict = {
        'Амурская область': 'Амурская обл.',
        'Астраханская область': 'Астраханская обл.',
        'Алтайский край': 'Алтайский край',
        'Брянская область': 'Брянская обл.',
        'Волгоградская область': 'Волгоградская обл.',
        'Воронежская область': 'Воронежская обл.',
        'Забайкальский край': None,
        'Иркутская область': 'Иркутская обл.',
        'Калининградская область': None,
        'Камчатский край': None,
        'Кемеровская область': 'Кемеровская обл.',
        'Костромская область': 'Костромская обл.',
        'Краснодарский край': 'Краснодарский край',
        'Красноярский край': 'Красноярский край',
        'Курганская область': 'Курганская обл.',
        'Курская область': 'Курская обл.',
        'Ленинградская область': 'Питер и ЛО',
        'Липецкая область': 'Липецкая обл.',
        'Магаданская область': None,
        'Мурманская область': 'Мурманская обл.',
        'Новгородская область': None,
        'Омская область': 'Омская обл.',
        'Орловская область': 'Орловская обл.',
        'Пермский край': 'Пермский край',
        'Псковская область': 'Псковская обл.',
        'Респ. Башкортостан': 'Башкортостан',
        'Респ. Дагестан': 'Дагестан',
        'Респ. Калмыкия': None,
        'Респ. Коми': 'Коми',
        'Респ. Марий Эл': 'Марий Эл',
        'Респ. Мордовия': 'Мордовия',
        'Респ. Саха (Якутия)': None,
        'Респ. Татарстан': 'Татарстан',
        'Респ. Тыва': None,
        'Республика Крым': 'Крым',
        'Ростовская область': 'Ростовская обл.',
        'Самарская область': 'Самарская обл.',
        'Сахалинская область': None,
        'Северная Осетия': 'Северная Осетия',
        'Ставропольский край': 'Ставропольский край',
        'Тверская область': 'Тверская обл.',
        'Томская область': 'Томская обл.',
        'Тульская область': 'Тульская обл.',
        'Тюменская область': 'Тюменская обл.',
        'Ульяновская область': 'Ульяновская обл.',
        'Челябинская область': 'Челябинская обл.',
        'Чувашская Респ.': 'Чувашия',
        'Чукотский округ': None,
        'Ярославская область': 'Ярославская обл.',
        'Другое': None,
        'ХМАО': 'Ханты-Мансийский АО',
        'ЯНАО': 'Ямало-Ненецкий АО',
    }

    try:
        bot_region = region_dict[forum_region]
    except Exception as e:
        logging.exception(e)
        bot_region = None

    return bot_region


# def save_user_region(user_id, region_name):
#    return None


def main(event, context):
    """main function triggered from communicate script via pyb/sub"""

    global user
    global cur
    global conn_psy

    user = ForumUser()

    pubsub_message = base64.b64decode(event['data']).decode('utf-8')

    encoded_to_ascii = eval(pubsub_message)
    data_in_ascii = encoded_to_ascii['data']
    message_in_ascii = data_in_ascii['message']
    tg_user_id, f_username = list(message_in_ascii)

    # initiate Prod Bot
    bot_token = get_secrets('bot_api_token__prod')
    bot = Bot(token=bot_token)  # noqa

    # log in to forum
    bot_forum_pass = get_secrets('forum_bot_password')
    login_into_forum(bot_forum_pass)

    user_found = False

    if message_in_ascii:
        f_usr_id = get_user_id(f_username)

        if f_usr_id != 0:
            block_of_user_data = get_user_attributes(f_usr_id)
            user_found = True

            if block_of_user_data:
                get_user_data(block_of_user_data)

    if user_found:
        bot_message = 'Посмотрите, Бот нашел следующий аккаунт на форуме, это Вы?\n'
        bot_message += 'username: ' + f_username + ', '
        if user.callsign:
            bot_message += 'позывной: ' + user.callsign + ', '
        # if user.region:
        #     bot_message += 'регион: ' + user.region + ', '
        if user.phone:
            bot_message += 'телефон оканчивается на ' + str(user.phone)[-5:] + ', '
        if user.age:
            bot_message += 'возраст: ' + str(user.age) + ', '
        if user.reg_date:
            bot_message += 'дата регистрации: ' + str(user.reg_date)[:-7] + ', '
        bot_message = bot_message[:-2]

        keyboard = [['да, это я'], ['нет, это не я'], ['в начало']]

        sql_connect_by_psycopg2()

        # Delete previous records for this user
        cur.execute("""DELETE FROM user_forum_attributes WHERE user_id=%s;""", (tg_user_id,))
        conn_psy.commit()

        # Add new record for this user
        cur.execute(
            """INSERT INTO user_forum_attributes
        (user_id, forum_user_id, status, timestamp, forum_username, forum_age, forum_sex, forum_region,
        forum_auto_num, forum_callsign, forum_phone, forum_reg_date)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);""",
            (
                tg_user_id,
                f_usr_id,
                'non-varified',
                datetime.datetime.now(),
                f_username,
                user.age,
                user.sex,
                user.region,
                user.auto_num,
                user.callsign,
                user.phone,
                user.reg_date,
            ),
        )
        conn_psy.commit()

        cur.execute("""SELECT forum_folder_num FROM user_regional_preferences WHERE user_id=%s""", (tg_user_id,))
        conn_psy.commit()
        user_has_region_set = True if cur.fetchone() else False
        logging.info(f'user_has_region_set = {user_has_region_set}')

        if not user_has_region_set and user.region:
            resulting_region_in_bot = match_user_region_from_forum_to_bot(user.region)  # noqa

        # TODO - here should be a block for saving user region pref. now we cannot do it, cuz user prefs are
        #  on folder level
        # if resulting_region_in_bot:
        # TODO ^^^

    else:
        bot_message = (
            'Бот не смог найти такого пользователя на форуме. '
            'Пожалуйста, проверьте правильность написания имени пользователя (логина). '
            'Важно, чтобы каждый знак в точности соответствовал тому, что указано в вашем профиле на форуме'
        )
        keyboard = [['в начало']]
        bot_request_aft_usr_msg = 'input_of_forum_username'

        sql_connect_by_psycopg2()

        try:
            cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (tg_user_id,))
            conn_psy.commit()
            cur.execute(
                """
                INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                """,
                (tg_user_id, datetime.datetime.now(), bot_request_aft_usr_msg),
            )
            conn_psy.commit()

        except Exception as e:
            logging.info('failed to update the last saved message from bot')
            logging.exception(e)

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    data = {'text': bot_message, 'reply_markup': reply_markup, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    process_sending_message_async(user_id=tg_user_id, data=data)

    # save bot's reply to incoming request
    if bot_message:
        cur.execute(
            """INSERT INTO dialogs (user_id, author, timestamp, message_text) values (%s, %s, %s, %s);""",
            (tg_user_id, 'bot', datetime.datetime.now(), bot_message),
        )
        conn_psy.commit()

    cur.close()
    conn_psy.close()

    return None
