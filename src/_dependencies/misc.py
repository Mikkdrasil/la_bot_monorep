import asyncio
import base64
import datetime
import json
import logging
import random
import time
import urllib.parse
from typing import Dict

import google.auth.transport.requests
import google.cloud.logging
import google.oauth2.id_token
import requests
from psycopg2.extensions import cursor
from telegram.ext import Application, ContextTypes

from _dependencies.commons import Topics, get_app_config, publish_to_pubsub


def notify_admin(message) -> None:
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub(Topics.topic_notify_admin, message)


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


def process_pubsub_message(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
    encoded_to_ascii = eval(received_message_from_pubsub)
    data_in_ascii = encoded_to_ascii['data']
    message_in_ascii = data_in_ascii['message']

    return message_in_ascii


def process_pubsub_message_v2(event: dict) -> str:
    """get message from pub/sub notification"""

    # receiving message text from pub/sub
    try:
        if 'data' in event:
            received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
            encoded_to_ascii = eval(received_message_from_pubsub)
            data_in_ascii = encoded_to_ascii['data']
            message_in_ascii = data_in_ascii['message']
        else:
            message_in_ascii = 'ERROR: I cannot read message from pub/sub'
    except:  # noqa
        message_in_ascii = 'ERROR: I cannot read message from pub/sub'

    logging.info(f'received message from pub/sub: {message_in_ascii}')

    return message_in_ascii


def process_pubsub_message_v3(event: dict) -> str:
    """convert incoming pub/sub message into regular data"""
    # TODO DOUBLE

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


def time_counter_since_search_start(start_time: datetime.datetime) -> tuple[str, int]:
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


def age_writer(age: int) -> str:
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


async def send_message_async(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=context.job.chat_id, **context.job.data)

    return None


async def prepare_message_for_async(user_id, data: Dict[str, str], bot_token: str) -> str:
    application = Application.builder().token(bot_token).build()
    job_queue = application.job_queue
    job_queue.run_once(send_message_async, 0, data=data, chat_id=user_id)

    async with application:
        await application.initialize()
        await application.start()
        await application.stop()
        await application.shutdown()

    return 'ok'


def process_sending_message_async_other_bot(user_id, data) -> None:
    # TODO same tokens or different?
    asyncio.run(prepare_message_for_async(user_id, data, bot_token=get_app_config().bot_api_token))


def process_sending_message_async(user_id: int, data) -> None:
    asyncio.run(prepare_message_for_async(user_id, data, bot_token=get_app_config().bot_api_token__prod))

    return None


def generate_random_function_id() -> int:
    """generates a random ID for every function – to track all function dependencies (no built-in ID in GCF)"""

    random_id = random.randint(100000000000, 999999999999)

    return random_id


def get_change_log_update_time(cur: cursor, change_log_id: int) -> datetime.datetime | None:
    """get he time of parsing of the change, saved in PSQL"""
    # TODO optimize/cache

    if not change_log_id:
        return None

    sql_text_psy = """
                    SELECT parsed_time 
                    FROM change_log 
                    WHERE id = %s;
                    /*action='getting_change_log_parsing_time' */;"""
    cur.execute(sql_text_psy, (change_log_id,))
    parsed_time = cur.fetchone()

    if not parsed_time:
        return None

    parsed_time = parsed_time[0]

    return parsed_time


def send_location_to_api(
    session: requests.Session, bot_token: str, user_id: int, params: dict
) -> requests.Response | None:
    """send location directly to Telegram API w/o any wrappers ar libraries"""

    try:
        latitude = ''
        longitude = ''
        if params:
            if 'latitude' in params.keys():
                latitude = f'&latitude={params["latitude"]}'
            if 'longitude' in params.keys():
                longitude = f'&longitude={params["longitude"]}'

        logging.info(latitude)
        logging.info(longitude)

        request_text = f'https://api.telegram.org/bot{bot_token}/sendLocation?chat_id={user_id}{latitude}{longitude}'

        r = session.get(request_text)

    except Exception as e:
        logging.exception(e)
        logging.info('Error in getting response from Telegram')
        r = None

    return r


def save_sending_status_to_notif_by_user(cur: cursor, message_id: int, result: str | None) -> None:
    """save the telegram sending status to sql table notif_by_user"""
    if not result:
        return 'failed'

    if result.startswith('cancelled'):
        result = 'cancelled'
    elif result.startswith('failed'):
        result = 'failed'

    if result not in {'completed', 'cancelled', 'failed'}:
        return

    sql_text_psy = f"""
                UPDATE notif_by_user
                SET {result} = %s
                WHERE message_id = %s;
                /*action='save_sending_status_to_notif_by_user_{result}' */
                ;"""

    cur.execute(sql_text_psy, (datetime.datetime.now(), message_id))


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


def get_triggering_function(message_from_pubsub: dict) -> int:
    """get a function_id of the function, which triggered this function (if available)"""

    triggered_by_func_id = 0
    try:
        if (
            message_from_pubsub
            and isinstance(message_from_pubsub, dict)
            and 'triggered_by_func_id' in message_from_pubsub.keys()
        ):
            triggered_by_func_id = int(message_from_pubsub['triggered_by_func_id'])

    except Exception as e:
        logging.exception(e)

    if triggered_by_func_id:
        logging.info(f'this function is triggered by func-id {triggered_by_func_id}')
    else:
        logging.info('triggering func_id was not determined')

    return triggered_by_func_id


def send_message_to_api(
    session: requests.Session, bot_token: str, user_id: int, message, params
) -> requests.Response | None:
    """send message directly to Telegram API w/o any wrappers ar libraries"""

    try:
        parse_mode = ''
        disable_web_page_preview = ''
        reply_markup = ''
        if params:
            if 'parse_mode' in params.keys():
                parse_mode = f'&parse_mode={params["parse_mode"]}'
            if 'disable_web_page_preview' in params.keys():
                disable_web_page_preview = f'&disable_web_page_preview={params["disable_web_page_preview"]}'
            if 'reply_markup' in params.keys():
                reply_markup_temp = params['reply_markup']
                reply_markup_json = json.dumps(reply_markup_temp)
                reply_markup_string = str(reply_markup_json)
                reply_markup_encoded = urllib.parse.quote(reply_markup_string)
                reply_markup = f'&reply_markup={reply_markup_encoded}'

                logging.info(f'{reply_markup_temp=}')
                logging.info(f'{reply_markup_json=}')
                logging.info(f'{reply_markup_string=}')
                logging.info(f'{reply_markup_encoded=}')
                logging.info(f'{reply_markup=}')

        message_encoded = urllib.parse.quote(message)

        request_text = (
            f'https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={user_id}'
            f'{parse_mode}{disable_web_page_preview}{reply_markup}&text={message_encoded}'
        )

        r = session.get(request_text)

    except Exception as e:
        logging.exception(e)
        logging.info('Error in getting response from Telegram')
        r = None

    return r


def process_response(user_id: int, response: requests.Response | None) -> str:
    """process response received as a result of Telegram API call while sending message/location"""

    try:
        if response.ok:
            logging.info(f'message to {user_id} was successfully sent')
            return 'completed'

        elif response.status_code == 400:  # Bad Request
            logging.info(f'Bad Request: message to {user_id} was not sent, {response.reason=}')
            logging.exception('BAD REQUEST')
            return 'cancelled_bad_request'

        elif response.status_code == 403:  # FORBIDDEN
            logging.info(f'Forbidden: message to {user_id} was not sent, {response.reason=}')
            action = None
            if response.text.find('bot was blocked by the user') != -1:
                action = 'block_user'
            if response.text.find('user is deactivated') != -1:
                action = 'delete_user'
            if action:
                message_for_pubsub = {'action': action, 'info': {'user': user_id}}
                publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)
                logging.info(f'Identified user id {user_id} to do {action}')
            return 'cancelled'

        elif 420 <= response.status_code <= 429:  # 'Flood Control':
            logging.info(f'Flood Control: message to {user_id} was not sent, {response.reason=}')
            logging.exception('FLOOD CONTROL')
            # fixme - try to get retry_after
            try:
                retry_after = response.parameters.retry_after
                print(f'ho-ho, we did it! 429 worked! {retry_after}')
            except:  # noqa
                pass
            # fixme ^^^
            time.sleep(5)  # to mitigate flood control
            return 'failed_flood_control'

        else:
            logging.info(f'UNKNOWN ERROR: message to {user_id} was not sent, {response.reason=}')
            logging.exception('UNKNOWN ERROR')
            return 'cancelled'

    except Exception as e:
        logging.info('Response is corrupted')
        logging.exception(e)
        return 'failed'
