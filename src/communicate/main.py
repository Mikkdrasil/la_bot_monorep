# ToDo later: user_callback["action"] == "search_follow_mode" заменить на "sfmw", "sfmb"

"""receives telegram messages from users, acts accordingly and sends back the reply"""

import asyncio
import datetime
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, List, Optional, Tuple, Union

import requests
from flask import Request
from psycopg2.extensions import cursor
from telegram import (
    Bot,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import Application, ContextTypes

from _dependencies.commons import (
    Topics,
    get_app_config,
    publish_to_pubsub,
    setup_google_logging,
    sql_connect_by_psycopg2,
)
from _dependencies.misc import (
    age_writer,
    notify_admin,
    process_sending_message_async,
    time_counter_since_search_start,
)
from communicate._utils.buttons import AllButtons, full_buttons_dict, search_button_row_ikb
from communicate._utils.database import (
    add_user_sys_role,
    check_if_new_user,
    check_if_user_has_no_regions,
    check_onboarding_step,
    compose_msg_on_all_last_searches,
    compose_user_preferences_message,
    delete_user_coordinates,
    delete_user_sys_role,
    distance_to_search,
    generate_yandex_maps_place_link,
    get_last_bot_msg,
    get_user_reg_folders_preferences,
    get_user_role,
    save_bot_reply_to_user,
    save_new_user,
    save_preference,
    save_user_coordinates,
    save_user_message_to_bot,
    save_user_pref_role,
    save_user_pref_topic_type,
    save_user_pref_urgency,
    show_user_coordinates,
    update_and_download_list_of_regions,
)
from communicate._utils.schemas import SearchSummary
from communicate._utils.services import (
    make_api_call,
    manage_age,
    manage_radius,
    manage_search_whiteness,
    manage_topic_type,
    process_block_unblock_user,
    process_response_of_api_call,
    save_onboarding_step,
    send_callback_answer_to_api,
)

setup_google_logging()

# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but jest informational warnings that there were retries, that's why we exclude them
logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


standard_modifier = {'on': '✅ ', 'off': '☐ '}


def compose_msg_on_all_last_searches_ikb(cur: cursor, region: int, user_id: int) -> List:
    """Compose a part of message on the list of recent searches"""
    # issue#425 it is ikb variant of the above function, returns data formated for inline keyboard
    # 1st element of returned list is general info and should be popped
    # rest elements are searches to be showed as inline buttons

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    ikb = []

    # download the list from SEARCHES sql table
    cur.execute(
        """SELECT s2.*, upswl.search_following_mode FROM 
            (SELECT search_forum_num, search_start_time, display_name, status, status, family_name, age 
            FROM searches 
            WHERE forum_folder_id=%(region)s 
            ORDER BY search_start_time DESC 
            LIMIT 20) s2 
        LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
        LEFT JOIN user_pref_search_whitelist upswl ON upswl.search_id=s2.search_forum_num and upswl.user_id=%(user_id)s
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""",
        {'region': region, 'user_id': user_id},
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
            search_following_mode,
        ) = list(line)

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age and search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        if not search.new_status:
            search.new_status = search.status

        if search.new_status in {'Ищем', 'Возобновлен'}:
            search.new_status = f'Ищем {time_counter_since_search_start(search.start_time)[0]}'

        ikb += search_button_row_ikb(
            search_following_mode,
            search.new_status,
            search.topic_id,
            search.display_name,
            f'{pre_url}{search.topic_id}',
        )
    return ikb


def compose_msg_on_active_searches_in_one_reg(cur: cursor, region: int, user_data) -> str:
    """Compose a part of message on the list of active searches in the given region with relation to user's coords"""

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    text = ''

    cur.execute(
        """SELECT s2.* FROM 
            (SELECT s.search_forum_num, s.search_start_time, s.display_name, sa.latitude, sa.longitude, 
            s.topic_type, s.family_name, s.age 
            FROM searches s 
            LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id 
            WHERE (s.status='Ищем' OR s.status='Возобновлен') 
                AND s.forum_folder_id=%s ORDER BY s.search_start_time DESC) s2 
        LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""",
        (region,),
    )
    searches_list = cur.fetchall()

    user_lat = None
    user_lon = None

    if user_data:
        user_lat = user_data[0]
        user_lon = user_data[1]

    for line in searches_list:
        search = SearchSummary()
        (
            search.topic_id,
            search.start_time,
            search.display_name,
            search_lat,
            search_lon,
            search.topic_type,
            search.name,
            search.age,
        ) = list(line)

        if time_counter_since_search_start(search.start_time)[1] >= 60:
            continue

        time_since_start = time_counter_since_search_start(search.start_time)[0]

        if user_lat and search_lat:
            dist = distance_to_search(search_lat, search_lon, user_lat, user_lon)
            dist_and_dir = f' {dist[1]} {dist[0]} км'
        else:
            dist_and_dir = ''

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        text += f'{time_since_start}{dist_and_dir} <a href="{pre_url}{search.topic_id}">{search.display_name}</a>\n'

    return text


def compose_msg_on_active_searches_in_one_reg_ikb(
    cur: cursor, region: int, user_data: Tuple[str, str], user_id: int
) -> List:
    """Compose a part of message on the list of active searches in the given region with relation to user's coords"""
    # issue#425 it is ikb variant of the above function, returns data formated for inline keyboard
    # 1st element of returned list is general info and should be popped
    # rest elements are searches to be showed as inline buttons

    pre_url = 'https://lizaalert.org/forum/viewtopic.php?t='
    ikb = []

    cur.execute(
        """SELECT s2.*, upswl.search_following_mode FROM 
            (SELECT s.search_forum_num, s.search_start_time, s.display_name, sa.latitude, sa.longitude, 
            s.topic_type, s.family_name, s.age 
            FROM searches s 
            LEFT JOIN search_coordinates sa ON s.search_forum_num = sa.search_id 
            WHERE (s.status='Ищем' OR s.status='Возобновлен') 
                AND s.forum_folder_id=%(region)s ORDER BY s.search_start_time DESC) s2 
        LEFT JOIN search_health_check shc ON s2.search_forum_num=shc.search_forum_num
        LEFT JOIN user_pref_search_whitelist upswl ON upswl.search_id=s2.search_forum_num and upswl.user_id=%(user_id)s
        WHERE (shc.status is NULL or shc.status='ok' or shc.status='regular') 
        ORDER BY s2.search_start_time DESC;""",
        {'region': region, 'user_id': user_id},
    )
    searches_list = cur.fetchall()

    user_lat = None
    user_lon = None

    if user_data:
        user_lat = user_data[0]
        user_lon = user_data[1]

    for line in searches_list:
        search = SearchSummary()
        (
            search.topic_id,
            search.start_time,
            search.display_name,
            search_lat,
            search_lon,
            search.topic_type,
            search.name,
            search.age,
            search_following_mode,
        ) = list(line)

        if time_counter_since_search_start(search.start_time)[1] >= 60:
            continue

        time_since_start = time_counter_since_search_start(search.start_time)[0]

        if user_lat and search_lat:
            dist = distance_to_search(search_lat, search_lon, user_lat, user_lon, False)
            dist_and_dir = f' {dist[1]} {dist[0]} км'
        else:
            dist_and_dir = ''

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        ikb += search_button_row_ikb(
            search_following_mode,
            f'{time_since_start}{dist_and_dir}',
            search.topic_id,
            search.display_name,
            f'{pre_url}{search.topic_id}',
        )
    return ikb


def compose_full_message_on_list_of_searches(
    cur: cursor, list_type: str, user_id: int, region: int, region_name: str
) -> str:
    """Compose a Final message on the list of searches in the given region"""

    msg = ''

    cur.execute('SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;', (user_id,))

    user_data = cur.fetchone()

    # combine the list of last 20 searches
    if list_type == 'all':
        msg += compose_msg_on_all_last_searches(cur, region)

        if msg:
            msg = (
                'Последние 20 поисков в разделе <a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a>:\n'
                + msg
            )

        else:
            msg = (
                'Не получается отобразить последние поиски в разделе '
                '<a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a>, что-то пошло не так, простите. Напишите об этом разработчику '
                'в <a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате '
                'в телеграм</a>, пожалуйста.'
            )

    # Combine the list of the latest active searches
    else:
        msg += compose_msg_on_active_searches_in_one_reg(cur, region, user_data)

        if msg:
            msg = (
                'Актуальные поиски за 60 дней в разделе <a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a>:\n'
                + msg
            )

        else:
            msg = (
                'В разделе <a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a> все поиски за последние 60 дней завершены.'
            )

    return msg


def compose_full_message_on_list_of_searches_ikb(
    cur: cursor, list_type: str, user_id: int, region: int, region_name: str
):  # issue#425
    """Compose a Final message on the list of searches in the given region"""
    # issue#425 This variant of the above function returns data in format used to compose inline keyboard
    # 1st element is caption
    # rest elements are searches in format to be showed as inline buttons

    ikb = []

    cur.execute('SELECT latitude, longitude FROM user_coordinates WHERE user_id=%s LIMIT 1;', (user_id,))

    user_data = cur.fetchone()

    url = f'https://lizaalert.org/forum/viewforum.php?f={region}'
    # combine the list of last 20 searches
    if list_type == 'all':
        ikb += compose_msg_on_all_last_searches_ikb(cur, region, user_id)
        logging.info('ikb += compose_msg_on_all_last_searches_ikb == ' + str(ikb))

        if len(ikb) > 0:
            msg = f'Посл. 20 поисков в {region_name}'
            ikb.insert(0, [{'text': msg, 'url': url}])
        else:
            msg = (
                'Не получается отобразить последние поиски в разделе '
                '<a href="https://lizaalert.org/forum/viewforum.php?f='
                + str(region)
                + '">'
                + region_name
                + '</a>, что-то пошло не так, простите. Напишите об этом разработчику '
                'в <a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате '
                'в телеграм</a>, пожалуйста.'
            )
            ikb = [[{'text': msg, 'url': url}]]

    # Combine the list of the latest active searches
    else:
        ikb += compose_msg_on_active_searches_in_one_reg_ikb(cur, region, user_data, user_id)
        logging.info(f'ikb += compose_msg_on_active_searches_in_one_reg_ikb == {ikb}; ({region=})')

        if len(ikb) > 0:
            msg = f'Акт. поиски за 60 дней в {region_name}'
            ikb.insert(0, [{'text': msg, 'url': url}])
        else:
            msg = f'Нет акт. поисков за 60 дней в {region_name}'
            ikb = [[{'text': msg, 'url': url}]]

    return ikb


# issue#425
def get_param_if_exists(upd: Update, func_input: str):
    """Return either value if exist or None. Used for messages with changing schema from telegram"""

    update = upd  # noqa

    try:
        func_output = eval(func_input)
    except:  # noqa
        func_output = None

    return func_output


# issue#425 inspired by manage_topic_type
# issue#425
def manage_search_follow_mode(
    cur: cursor, user_id: int, user_callback: dict, callback_id: str, callback_query, bot_token: str
) -> str | None:
    """Switches search following mode on/off"""

    logging.info(f'{callback_query=}, {user_id=}')
    # when user pushed INLINE BUTTON for topic following
    if user_callback and user_callback['action'] == 'search_follow_mode_on':
        set_search_follow_mode(cur, user_id, True)
        bot_message = 'Режим выбора поисков для отслеживания включен.'

    elif user_callback and user_callback['action'] == 'search_follow_mode_off':
        set_search_follow_mode(cur, user_id, False)
        bot_message = 'Режим выбора поисков для отслеживания отключен.'

    send_callback_answer_to_api(bot_token, callback_id, bot_message)

    return bot_message


def manage_if_moscow(
    cur,
    user_id,
    username,
    got_message,
    b_reg_moscow,
    b_reg_not_moscow,
    reply_markup,
    keyboard_fed_dist_set,
    bot_message,
    user_role,
):
    """act if user replied either user from Moscow region or from another one"""

    # if user Region is Moscow
    if got_message == b_reg_moscow:
        save_onboarding_step(user_id, username, 'moscow_replied')
        save_onboarding_step(user_id, username, 'region_set')
        save_user_pref_topic_type(cur, user_id, 'default', user_role)

        if check_if_user_has_no_regions(cur, user_id):
            # add the New User into table user_regional_preferences
            # region is Moscow for Active Searches & InfoPod
            cur.execute(
                """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values
                (%s, %s);""",
                (user_id, 276),
            )
            cur.execute(
                """INSERT INTO user_regional_preferences (user_id, forum_folder_num) values
                (%s, %s);""",
                (user_id, 41),
            )
            cur.execute(
                """INSERT INTO user_pref_region (user_id, region_id) values
                (%s, %s);""",
                (user_id, 1),
            )

    # if region is NOT Moscow
    elif got_message == b_reg_not_moscow:
        save_onboarding_step(user_id, username, 'moscow_replied')

        bot_message = (
            'Спасибо, тогда для корректной работы Бота, пожалуйста, выберите свой регион: '
            'сначала обозначьте Федеральный Округ, '
            'а затем хотя бы один Регион поисков, чтобы отслеживать поиски в этом регионе. '
            'Вы в любой момент сможете изменить '
            'список регионов через настройки бота.'
        )
        reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)

    else:
        bot_message = None
        reply_markup = None

    return bot_message, reply_markup


def manage_linking_to_forum(
    cur: cursor,
    got_message: str,
    user_id: int,
    b_set_forum_nick: str,
    b_back_to_start: str,
    bot_request_bfr_usr_msg: str,
    b_admin_menu: str,
    b_test_menu: str,
    b_yes_its_me: str,
    b_no_its_not_me: str,
    b_settings: str,
    reply_markup_main: ReplyKeyboardMarkup,
) -> Tuple[str, ReplyKeyboardMarkup, Optional[str]]:
    """manage all interactions regarding connection of telegram and forum user accounts"""

    bot_message, reply_markup, bot_request_aft_usr_msg = None, None, None

    if got_message == b_set_forum_nick:
        # TODO: if user_is linked to forum so
        cur.execute(
            """SELECT forum_username, forum_user_id 
                       FROM user_forum_attributes 
                       WHERE status='verified' AND user_id=%s 
                       ORDER BY timestamp DESC 
                       LIMIT 1;""",
            (user_id,),
        )
        saved_forum_user = cur.fetchone()

        if not saved_forum_user:
            bot_message = (
                'Бот сможет быть еще полезнее, эффективнее и быстрее, если указать ваш аккаунт на форуме '
                'lizaalert.org\n\n'
                'Для этого просто введите ответным сообщением своё имя пользователя (логин).\n\n'
                'Если возникнут ошибки при распознавании – просто скопируйте имя с форума и '
                'отправьте боту ответным сообщением.'
            )
            keyboard = [[b_back_to_start]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            bot_request_aft_usr_msg = 'input_of_forum_username'

        else:
            saved_forum_username, saved_forum_user_id = list(saved_forum_user)

            bot_message = (
                f'Ваш телеграм уже привязан к аккаунту '
                f'<a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
                f'{saved_forum_user_id}">{saved_forum_username}</a> '
                f'на форуме ЛизаАлерт. Больше никаких действий касательно аккаунта на форуме не требуется:)'
            )
            keyboard = [[b_settings], [b_back_to_start]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    elif (
        bot_request_bfr_usr_msg == 'input_of_forum_username'
        and got_message not in {b_admin_menu, b_back_to_start, b_test_menu}
        and len(got_message.split()) < 4
    ):
        message_for_pubsub = [user_id, got_message]
        publish_to_pubsub(Topics.parse_user_profile_from_forum, message_for_pubsub)
        bot_message = 'Сейчас посмотрю, это может занять до 10 секунд...'
        keyboard = [[b_back_to_start]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    elif got_message in {b_yes_its_me}:
        # Write "verified" for user
        cur.execute(
            """UPDATE user_forum_attributes SET status='verified'
                WHERE user_id=%s and timestamp =
                (SELECT MAX(timestamp) FROM user_forum_attributes WHERE user_id=%s);""",
            (user_id, user_id),
        )

        bot_message = (
            'Отлично, мы записали: теперь бот будет понимать, кто вы на форуме.\nЭто поможет '
            'вам более оперативно получать сообщения о поисках, по которым вы оставляли '
            'комментарии на форуме.'
        )
        keyboard = [[b_settings], [b_back_to_start]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    elif got_message == b_no_its_not_me:
        bot_message = (
            'Пожалуйста, тщательно проверьте написание вашего ника на форуме '
            '(кириллица/латиница, без пробела в конце) и введите его заново'
        )
        keyboard = [[b_set_forum_nick], [b_back_to_start]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        bot_request_aft_usr_msg = 'input_of_forum_username'

    elif got_message == b_back_to_start:
        bot_message = 'возвращаемся в главное меню'
        reply_markup = reply_markup_main

    return bot_message, reply_markup, bot_request_aft_usr_msg


async def leave_chat_async(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.leave_chat(chat_id=context.job.chat_id)

    return None


async def prepare_message_for_leave_chat_async(user_id):
    # TODO DOUBLE
    bot_token = get_app_config().bot_api_token__prod
    application = Application.builder().token(bot_token).build()
    job_queue = application.job_queue
    job_queue.run_once(leave_chat_async, 0, chat_id=user_id)

    async with application:
        await application.initialize()
        await application.start()
        await application.stop()
        await application.shutdown()

    return 'ok'


def process_leaving_chat_async(user_id) -> None:
    asyncio.run(prepare_message_for_leave_chat_async(user_id))

    return None


def get_last_bot_message_id(response: requests.Response) -> int:
    """Get the message id of the bot's message that was just sent"""

    try:
        message_id = response.json()['result']['message_id']

    except Exception as e:  # noqa
        message_id = None

    return message_id


def inline_processing(cur, response, params) -> None:
    """process the response got from inline buttons interactions"""

    if not response or 'chat_id' not in params.keys():
        return None

    chat_id = params['chat_id']
    sent_message_id = get_last_bot_message_id(response)

    if 'reply_markup' in params.keys() and 'inline_keyboard' in params['reply_markup'].keys():
        prev_message_id = get_last_user_inline_dialogue(cur, chat_id)
        logging.info(f'{prev_message_id=}')
        save_last_user_inline_dialogue(cur, chat_id, sent_message_id)

    return None


def send_message_to_api(bot_token, user_id, message, params):
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
                rep_as_str = str(json.dumps(params['reply_markup']))
                reply_markup = f'&reply_markup={urllib.parse.quote(rep_as_str)}'
        message_encoded = f'&text={urllib.parse.quote(message)}'

        request_text = (
            f'https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={user_id}'
            f'{message_encoded}{parse_mode}{disable_web_page_preview}{reply_markup}'
        )

        with requests.Session() as session:
            response = session.get(request_text)
            logging.info(str(response))

    except Exception as e:
        logging.exception(e)
        logging.info('Error in getting response from Telegram')
        response = None

    result = process_response_of_api_call(user_id, response)

    return result


def api_callback_edit_inline_keyboard(bot_token: str, callback_query: dict, reply_markup: dict, user_id: str) -> str:
    """send a notification when inline button is pushed directly to Telegram API w/o any wrappers ar libraries"""
    if reply_markup and not isinstance(reply_markup, dict):
        reply_markup_dict = reply_markup.to_dict()

    params = {
        'chat_id': callback_query['message']['chat']['id'],
        'message_id': callback_query['message']['message_id'],
        'text': callback_query['message']['text'],
        'reply_markup': reply_markup_dict,
    }

    response = make_api_call('editMessageText', bot_token, params, 'api_callback_edit_inline_keyboard')
    logging.info(f'After make_api_call(editMessageText): {response.json()=}')
    result = process_response_of_api_call(user_id, response)
    return result


def get_the_update(bot: Bot, request: Request) -> Update | None:
    """converts a request to an update"""

    try:
        update = Update.de_json(request.get_json(force=True), bot)
    except Exception as e:
        logging.exception(e)
        logging.error('request received has no update')
        update = None

    logging.info(f'update received: {request.get_json(force=True)}')

    return update


def get_basic_update_parameters(update: Update):
    """decompose the incoming update into the key parameters"""

    user_new_status = get_param_if_exists(update, 'update.my_chat_member.new_chat_member.status')
    timer_changed = get_param_if_exists(update, 'update.message.message_auto_delete_timer_changed')
    photo = get_param_if_exists(update, 'update.message.photo')
    document = get_param_if_exists(update, 'update.message.document')
    voice = get_param_if_exists(update, 'update.message.voice')
    contact = get_param_if_exists(update, 'update.message.contact')
    inline_query = get_param_if_exists(update, 'update.inline_query')
    sticker = get_param_if_exists(update, 'update.message.sticker.file_id')
    user_latitude = get_param_if_exists(update, 'update.effective_message.location.latitude')
    user_longitude = get_param_if_exists(update, 'update.effective_message.location.longitude')
    got_message = get_param_if_exists(update, 'update.effective_message.text')

    channel_type = get_param_if_exists(update, 'update.edited_channel_post.chat.type')
    if not channel_type:
        channel_type = get_param_if_exists(update, 'update.channel_post.chat.type')
    if not channel_type:
        channel_type = get_param_if_exists(update, 'update.my_chat_member.chat.type')

    # the purpose of this bot - sending messages to unique users, this way
    # chat_id is treated as user_id and vice versa (which is not true in general)

    username = get_param_if_exists(update, 'update.effective_user.username')
    if not username:
        username = get_param_if_exists(update, 'update.effective_message.from_user.username')

    user_id = get_param_if_exists(update, 'update.effective_user.id')
    if not user_id:
        logging.exception('EFFECTIVE USER.ID IS NOT GIVEN!')
        user_id = get_param_if_exists(update, 'update.effective_message.from_user.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.effective_message.chat.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.edited_channel_post.chat.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.my_chat_member.chat.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.inline_query.from.id')
    if not user_id:
        logging.info('failed to define user_id')

    # FIXME – 17.11.2023 – playing with getting inline buttons interactions
    callback_query = get_param_if_exists(update, 'update.callback_query')
    callback_query_id = get_param_if_exists(update, 'update.callback_query.id')

    logging.info(f'get_basic_update_parameters..callback_query==, {str(callback_query)}')
    got_hash = None
    got_callback = None
    if callback_query:
        callback_data_text = callback_query.data
        try:
            got_callback = eval(callback_data_text)
            got_hash = got_callback.get('hash')
        except Exception as e:
            logging.exception(e)
            notify_admin(f'callback dict was not recognized for {callback_data_text=}')
        logging.info(f'get_basic_update_parameters..{got_callback=}, {got_hash=} from {callback_data_text=}')
    # FIXME ^^^

    return (
        user_new_status,
        timer_changed,
        photo,
        document,
        voice,
        contact,
        inline_query,
        sticker,
        user_latitude,
        user_longitude,
        got_message,
        channel_type,
        username,
        user_id,
        got_hash,
        got_callback,
        callback_query_id,
        callback_query,
    )


def process_unneeded_messages(
    update, user_id, timer_changed, photo, document, voice, sticker, channel_type, contact, inline_query
):
    """process messages which are not a part of designed dialogue"""

    # CASE 2 – when user changed auto-delete setting in the bot
    if timer_changed:
        logging.info('user changed auto-delete timer settings')

    # CASE 3 – when user sends a PHOTO or attached DOCUMENT or VOICE message
    elif photo or document or voice or sticker:
        logging.debug('user sends photos to bot')

        bot_message = (
            'Спасибо, интересное! Однако, бот работает только с текстовыми командами. '
            'Пожалуйста, воспользуйтесь текстовыми кнопками бота, находящимися на '
            'месте обычной клавиатуры телеграм.'
        )
        data = {'text': bot_message}
        process_sending_message_async(user_id=user_id, data=data)

    # CASE 4 – when some Channel writes to bot
    elif channel_type and user_id < 0:
        notify_admin('[comm]: INFO: CHANNEL sends messages to bot!')

        try:
            process_leaving_chat_async(user_id)
            notify_admin(f'[comm]: INFO: we have left the CHANNEL {user_id}')

        except Exception as e:
            logging.info(f'[comm]: Leaving channel was not successful: {user_id}')
            logging.exception(e)
            notify_admin(f'[comm]: Leaving channel was not successful: {user_id}')

    # CASE 5 – when user sends Contact
    elif contact:
        bot_message = (
            'Спасибо, буду знать. Вот только бот не работает с контактами и отвечает '
            'только на определенные текстовые команды.'
        )
        data = {'text': bot_message}
        process_sending_message_async(user_id=user_id, data=data)

    # CASE 6 – when user mentions bot as @LizaAlert_Searcher_Bot in another telegram chat. Bot should do nothing
    elif inline_query:
        notify_admin('[comm]: User mentioned bot in some chats')
        logging.info(f'bot was mentioned in other chats: {update}')

    return None


def get_coordinates_from_string(got_message: str, lat_placeholder, lon_placeholder) -> Tuple[float, float]:
    """gets coordinates from string"""

    user_latitude, user_longitude = None, None
    # Check if user input is in format of coordinates
    # noinspection PyBroadException
    try:
        numbers = [float(s) for s in re.findall(r'-?\d+\.?\d*', got_message)]
        if numbers and len(numbers) > 1 and 30 < numbers[0] < 80 and 10 < numbers[1] < 190:
            user_latitude = numbers[0]
            user_longitude = numbers[1]
    except Exception:
        logging.info(f'manual coordinates were not identified from string {got_message}')

    if not (user_latitude and user_longitude):
        user_latitude = lat_placeholder
        user_longitude = lon_placeholder

    return user_latitude, user_longitude


def process_user_coordinates(
    cur: cursor,
    user_id: int,
    user_latitude: float,
    user_longitude: float,
    b_coords_check: str,
    b_coords_del: str,
    b_back_to_start: str,
    bot_request_aft_usr_msg: str,
) -> Optional[Any]:
    """process coordinates which user sent to bot"""

    save_user_coordinates(cur, user_id, user_latitude, user_longitude)

    bot_message = 'Ваши "домашние координаты" сохранены:\n'
    bot_message += generate_yandex_maps_place_link(user_latitude, user_longitude, 'coords')
    bot_message += (
        '\nТеперь для всех поисков, где удастся распознать координаты штаба или '
        'населенного пункта, будет указываться направление и расстояние по '
        'прямой от ваших "домашних координат".'
    )

    keyboard_settings = [[b_coords_check], [b_coords_del], [b_back_to_start]]
    reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)

    data = {'text': bot_message, 'reply_markup': reply_markup, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    process_sending_message_async(user_id=user_id, data=data)
    # msg_sent_by_specific_code = True

    # saving the last message from bot
    if not bot_request_aft_usr_msg:
        bot_request_aft_usr_msg = 'not_defined'

    try:
        cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))

        cur.execute(
            """INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);""",
            (user_id, datetime.datetime.now(), bot_request_aft_usr_msg),
        )

    except Exception as e:
        logging.info('failed to update the last saved message from bot')
        logging.exception(e)

    save_bot_reply_to_user(cur, user_id, bot_message)

    return None


def run_onboarding(user_id: int, username: str, onboarding_step_id: int, got_message: str) -> int:
    """part of the script responsible for orchestration of activities for non-finally-onboarded users"""

    if onboarding_step_id == 21:  # region_set
        # mark that onboarding is finished
        if got_message:
            save_onboarding_step(user_id, username, 'finished')
            onboarding_step_id = 80

    return onboarding_step_id


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


def get_last_user_inline_dialogue(cur, user_id: int) -> list:
    """Get from DB the user's last interaction via inline buttons"""

    cur.execute("""SELECT message_id FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))
    message_id_lines = cur.fetchall()

    message_id_list = []
    if message_id_lines and len(message_id_lines) > 0:
        for message_id_line in message_id_lines:
            message_id_list.append(message_id_line[0])

    return message_id_list


def delete_last_user_inline_dialogue(cur, user_id: int) -> None:
    """Delete form DB the user's last interaction via inline buttons"""

    cur.execute("""DELETE FROM communications_last_inline_msg WHERE user_id=%s;""", (user_id,))
    return None


def get_search_follow_mode(cur, user_id: int):
    cur.execute("""SELECT filter_name FROM user_pref_search_filtering WHERE user_id=%s LIMIT 1;""", (user_id,))
    result_fetched = cur.fetchone()
    result = result_fetched and 'whitelist' in result_fetched[0]
    return result


def set_search_follow_mode(cur: cursor, user_id: int, new_value: bool) -> None:
    filter_name_value = ['whitelist'] if new_value else ['']
    logging.info(f'{filter_name_value=}')
    cur.execute(
        """INSERT INTO user_pref_search_filtering (user_id, filter_name) values (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET filter_name=%s;""",
        (user_id, filter_name_value, filter_name_value),
    )
    return None


def main(request: Request) -> str:
    """Main function to orchestrate the whole script"""

    if request.method != 'POST':
        logging.error(f'non-post request identified {request}')
        return 'it was not post request'

    bot_token = get_app_config().bot_api_token__prod
    bot = Bot(token=bot_token)
    update = get_the_update(bot, request)
    return process_update(update)


def process_update(update: Update) -> str:
    bot_token = get_app_config().bot_api_token__prod

    (
        user_new_status,
        timer_changed,
        photo,
        document,
        voice,
        contact,
        inline_query,
        sticker,
        user_latitude,
        user_longitude,
        got_message,
        channel_type,
        username,
        user_id,
        got_hash,
        got_callback,
        callback_query_id,
        callback_query,
    ) = get_basic_update_parameters(update)

    logging.info(f'after get_basic_update_parameters:  {got_callback=}')

    if (
        timer_changed
        or photo
        or document
        or voice
        or sticker
        or (channel_type and user_id < 0)
        or contact
        or inline_query
    ):
        process_unneeded_messages(
            update, user_id, timer_changed, photo, document, voice, sticker, channel_type, contact, inline_query
        )
        return 'finished successfully. it was useless message for bot'

    if user_new_status in {'kicked', 'member'}:
        process_block_unblock_user(user_id, user_new_status)
        return 'finished successfully. it was a system message on bot block/unblock'

    b = AllButtons(full_buttons_dict)

    # Buttons & Keyboards
    # Start & Main menu
    c_start = '/start'
    c_view_act_searches = '/view_act_searches'
    c_view_latest_searches = '/view_latest_searches'
    c_settings = '/settings'
    c_other = '/other'
    c_map = '/map'

    b_role_iam_la = 'я состою в ЛизаАлерт'
    b_role_want_to_be_la = 'я хочу помогать ЛизаАлерт'
    b_role_looking_for_person = 'я ищу человека'
    b_role_other = 'у меня другая задача'
    b_role_secret = 'не хочу говорить'

    b_orders_done = 'да, заявки поданы'
    b_orders_tbd = 'нет, но я хочу продолжить'

    # TODO - WIP: FORUM
    b_forum_check_nickname = 'указать свой nickname с форума'  # noqa
    b_forum_dont_have = 'у меня нет аккаунта на форуме ЛА'  # noqa
    b_forum_dont_want = 'пропустить / не хочу говорить'  # noqa
    # TODO ^^^

    b_pref_urgency_highest = 'самым первым (<2 минуты)'
    b_pref_urgency_high = 'пораньше (<5 минут)'
    b_pref_urgency_medium = 'могу ждать (<10 минут)'
    b_pref_urgency_low = 'не сильно важно (>10 минут)'

    b_yes_its_me = 'да, это я'
    b_no_its_not_me = 'нет, это не я'

    b_view_act_searches = 'посмотреть актуальные поиски'
    b_settings = 'настроить бот'
    b_other = 'другие возможности'
    b_map = '🔥Карта Поисков 🔥'
    keyboard_main = [[b_map], [b_view_act_searches], [b_settings], [b_other]]
    reply_markup_main = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)

    # Settings menu
    b_set_pref_notif_type = 'настроить виды уведомлений'
    b_set_pref_coords = 'настроить "домашние координаты"'
    b_set_pref_radius = 'настроить максимальный радиус'
    b_set_pref_age = 'настроить возрастные группы БВП'
    b_set_pref_urgency = 'настроить скорость уведомлений'  # <-- TODO: likely to be removed as redundant
    b_set_pref_role = 'настроить вашу роль'  # <-- TODO # noqa
    b_set_forum_nick = 'связать аккаунты бота и форума'
    b_change_forum_nick = 'изменить аккаунт форума'  # noqa
    b_set_topic_type = 'настроить вид поисков'

    b_back_to_start = 'в начало'

    # Settings - notifications
    b_act_all = 'включить: все уведомления'
    b_act_new_search = 'включить: о новых поисках'
    b_act_stat_change = 'включить: об изменениях статусов'
    b_act_all_comments = 'включить: о всех новых комментариях'
    b_act_inforg_com = 'включить: о комментариях Инфорга'
    b_act_field_trips_new = 'включить: о новых выездах'
    b_act_field_trips_change = 'включить: об изменениях в выездах'
    b_act_coords_change = 'включить: о смене места штаба'
    b_act_first_post_change = 'включить: об изменениях в первом посте'
    b_deact_all = 'настроить более гибко'
    b_deact_new_search = 'отключить: о новых поисках'
    b_deact_stat_change = 'отключить: об изменениях статусов'
    b_deact_all_comments = 'отключить: о всех новых комментариях'
    b_deact_inforg_com = 'отключить: о комментариях Инфорга'
    b_deact_field_trips_new = 'отключить: о новых выездах'
    b_deact_field_trips_change = 'отключить: об изменениях в выездах'
    b_deact_coords_change = 'отключить: о смене места штаба'
    b_deact_first_post_change = 'отключить: об изменениях в первом посте'

    # Settings - coordinates
    b_coords_auto_def = KeyboardButton(text='автоматически определить "домашние координаты"', request_location=True)
    b_coords_man_def = 'ввести "домашние координаты" вручную'
    b_coords_check = 'посмотреть сохраненные "домашние координаты"'
    b_coords_del = 'удалить "домашние координаты"'

    # Dialogue if Region – is Moscow
    b_reg_moscow = 'да, Москва – мой регион'
    b_reg_not_moscow = 'нет, я из другого региона'

    # Settings - Federal Districts
    b_fed_dist_dal_vos = 'Дальневосточный ФО'
    b_fed_dist_privolz = 'Приволжский ФО'
    b_fed_dist_sev_kaz = 'Северо-Кавказский ФО'
    b_fed_dist_sev_zap = 'Северо-Западный ФО'
    b_fed_dist_sibiria = 'Сибирский ФО'
    b_fed_dist_uralsky = 'Уральский ФО'
    b_fed_dist_central = 'Центральный ФО'
    b_fed_dist_yuzhniy = 'Южный ФО'
    b_fed_dist_other_r = 'Прочие поиски по РФ'
    b_fed_dist_pick_other = 'выбрать другой Федеральный Округ'
    keyboard_fed_dist_set = [
        [b_fed_dist_dal_vos],
        [b_fed_dist_privolz],
        [b_fed_dist_sev_kaz],
        [b_fed_dist_sev_zap],
        [b_fed_dist_sibiria],
        [b_fed_dist_uralsky],
        [b_fed_dist_central],
        [b_fed_dist_yuzhniy],
        [b_fed_dist_other_r],
        [b_back_to_start],
    ]

    # Settings - Dalnevostochniy Fed Dist - Regions
    b_reg_buryatiya = 'Бурятия'
    b_reg_prim_kray = 'Приморский край'
    b_reg_habarovsk = 'Хабаровский край'
    b_reg_amur = 'Амурская обл.'
    b_reg_dal_vost_other = 'Прочие поиски по ДФО'
    keyboard_dal_vost_reg_choice = [
        [b_reg_buryatiya],
        [b_reg_prim_kray],
        [b_reg_habarovsk],
        [b_reg_amur],
        [b_reg_dal_vost_other],
        [b_fed_dist_pick_other],
        [b_back_to_start],
    ]

    # Settings - Privolzhskiy Fed Dist - Regions
    b_reg_bashkorkostan = 'Башкортостан'
    b_reg_kirov = 'Кировская обл.'
    b_reg_mariy_el = 'Марий Эл'
    b_reg_mordovia = 'Мордовия'
    b_reg_nizhniy = 'Нижегородская обл.'
    b_reg_orenburg = 'Оренбургская обл.'
    b_reg_penza = 'Пензенская обл.'
    b_reg_perm = 'Пермский край'
    b_reg_samara = 'Самарская обл.'
    b_reg_saratov = 'Саратовская обл.'
    b_reg_tatarstan = 'Татарстан'
    b_reg_udmurtiya = 'Удмуртия'
    b_reg_ulyanovsk = 'Ульяновская обл.'
    b_reg_chuvashiya = 'Чувашия'
    b_reg_privolz_other = 'Прочие поиски по ПФО'
    keyboard_privolz_reg_choice = [
        [b_reg_bashkorkostan],
        [b_reg_kirov],
        [b_reg_mariy_el],
        [b_reg_mordovia],
        [b_reg_nizhniy],
        [b_reg_orenburg],
        [b_reg_penza],
        [b_reg_perm],
        [b_reg_samara],
        [b_reg_saratov],
        [b_reg_tatarstan],
        [b_reg_udmurtiya],
        [b_reg_ulyanovsk],
        [b_reg_chuvashiya],
        [b_reg_privolz_other],
        [b_fed_dist_pick_other],
        [b_back_to_start],
    ]

    # Settings - Severo-Kavkazskiy Fed Dist - Regions
    b_reg_dagestan = 'Дагестан'
    b_reg_stavropol = 'Ставропольский край'
    b_reg_chechnya = 'Чечня'
    b_reg_kabarda = 'Кабардино-Балкария'
    b_reg_ingushetia = 'Ингушетия'
    b_reg_sev_osetia = 'Северная Осетия'
    b_reg_sev_kav_other = 'Прочие поиски по СКФО'
    keyboard_sev_kav_reg_choice = [
        [b_reg_dagestan],
        [b_reg_stavropol],
        [b_reg_chechnya],
        [b_reg_kabarda],
        [b_reg_ingushetia],
        [b_reg_sev_osetia],
        [b_reg_sev_kav_other],
        [b_fed_dist_pick_other],
        [b_back_to_start],
    ]

    # Settings - Severo-Zapadniy Fed Dist - Regions
    b_reg_vologda = 'Вологодская обл.'
    b_reg_karelia = 'Карелия'
    b_reg_komi = 'Коми'
    b_reg_piter = 'Ленинградская обл.'
    b_reg_murmansk = 'Мурманская обл.'
    b_reg_pskov = 'Псковская обл.'
    b_reg_archangelsk = 'Архангельская обл.'
    b_reg_sev_zap_other = 'Прочие поиски по СЗФО'
    keyboard_sev_zap_reg_choice = [
        [b_reg_vologda],
        [b_reg_komi],
        [b_reg_karelia],
        [b_reg_piter],
        [b_reg_murmansk],
        [b_reg_pskov],
        [b_reg_archangelsk],
        [b_reg_sev_zap_other],
        [b_fed_dist_pick_other],
        [b_back_to_start],
    ]

    # Settings - Sibirskiy Fed Dist - Regions
    b_reg_altay = 'Алтайский край'
    b_reg_irkutsk = 'Иркутская обл.'
    b_reg_kemerovo = 'Кемеровская обл.'
    b_reg_krasnoyarsk = 'Красноярский край'
    b_reg_novosib = 'Новосибирская обл.'
    b_reg_omsk = 'Омская обл.'
    b_reg_tomsk = 'Томская обл.'
    b_reg_hakasiya = 'Хакасия'
    b_reg_sibiria_reg_other = 'Прочие поиски по СФО'
    keyboard_sibiria_reg_choice = [
        [b_reg_altay],
        [b_reg_irkutsk],
        [b_reg_kemerovo],
        [b_reg_krasnoyarsk],
        [b_reg_novosib],
        [b_reg_omsk],
        [b_reg_tomsk],
        [b_reg_hakasiya],
        [b_reg_sibiria_reg_other],
        [b_fed_dist_pick_other],
        [b_back_to_start],
    ]

    # Settings - Uralskiy Fed Dist - Regions
    b_reg_ekat = 'Свердловская обл.'
    b_reg_kurgan = 'Курганская обл.'
    b_reg_tyumen = 'Тюменская обл.'
    b_reg_hanty_mansi = 'Ханты-Мансийский АО'
    b_reg_chelyabinks = 'Челябинская обл.'
    b_reg_yamal = 'Ямало-Ненецкий АО'
    b_reg_urals_reg_other = 'Прочие поиски по УФО'
    keyboard_urals_reg_choice = [
        [b_reg_ekat],
        [b_reg_kurgan],
        [b_reg_tyumen],
        [b_reg_hanty_mansi],
        [b_reg_chelyabinks],
        [b_reg_yamal],
        [b_reg_urals_reg_other],
        [b_fed_dist_pick_other],
        [b_back_to_start],
    ]

    # Settings - Central Fed Dist - Regions
    b_reg_belogorod = 'Белгородская обл.'
    b_reg_bryansk = 'Брянская обл.'
    b_reg_vladimir = 'Владимирская обл.'
    b_reg_voronezh = 'Воронежская обл.'
    b_reg_ivanovo = 'Ивановская обл.'
    b_reg_kaluga = 'Калужская обл.'
    b_reg_kostroma = 'Костромская обл.'
    b_reg_kursk = 'Курская обл.'
    b_reg_lipetsk = 'Липецкая обл.'
    b_reg_msk_act = 'Москва и МО: Активные Поиски'
    b_reg_msk_inf = 'Москва и МО: Инфо Поддержка'
    b_reg_orel = 'Орловская обл.'
    b_reg_ryazan = 'Рязанская обл.'
    b_reg_smolensk = 'Смоленская обл.'
    b_reg_tambov = 'Тамбовская обл.'
    b_reg_tver = 'Тверская обл.'
    b_reg_tula = 'Тульская обл.'
    b_reg_yaroslavl = 'Ярославская обл.'
    b_reg_central_reg_other = 'Прочие поиски по ЦФО'
    keyboard_central_reg_choice = [
        [b_reg_belogorod],
        [b_reg_bryansk],
        [b_reg_vladimir],
        [b_reg_voronezh],
        [b_reg_ivanovo],
        [b_reg_kaluga],
        [b_reg_kostroma],
        [b_reg_kursk],
        [b_reg_lipetsk],
        [b_reg_msk_act],
        [b_reg_msk_inf],
        [b_reg_orel],
        [b_reg_ryazan],
        [b_reg_smolensk],
        [b_reg_tambov],
        [b_reg_tver],
        [b_reg_tula],
        [b_reg_yaroslavl],
        [b_reg_central_reg_other],
        [b_fed_dist_pick_other],
        [b_back_to_start],
    ]

    # Settings - Yuzhniy Fed Dist - Regions
    b_reg_adygeya = 'Адыгея'
    b_reg_astrahan = 'Астраханская обл.'
    b_reg_volgograd = 'Волгоградская обл.'
    b_reg_krasnodar = 'Краснодарский край'
    b_reg_krym = 'Крым'
    b_reg_rostov = 'Ростовская обл.'
    b_reg_yuzhniy_reg_other = 'Прочие поиски по ЮФО'
    keyboard_yuzhniy_reg_choice = [
        [b_reg_adygeya],
        [b_reg_astrahan],
        [b_reg_volgograd],
        [b_reg_krasnodar],
        [b_reg_krym],
        [b_reg_rostov],
        [b_reg_yuzhniy_reg_other],
        [b_fed_dist_pick_other],
        [b_back_to_start],
    ]

    # Settings - Fed Dist - Regions
    b_menu_set_region = 'настроить регион поисков'

    full_list_of_regions = (
        keyboard_dal_vost_reg_choice[:-1]
        + keyboard_privolz_reg_choice[:-1]
        + keyboard_sev_kav_reg_choice[:-1]
        + keyboard_sev_zap_reg_choice[:-1]
        + keyboard_sibiria_reg_choice[:-1]
        + keyboard_urals_reg_choice[:-1]
        + keyboard_central_reg_choice[:-1]
        + keyboard_yuzhniy_reg_choice[:-1]
        + [[b_fed_dist_other_r]]
    )  # noqa – for strange pycharm indent warning
    full_dict_of_regions = {word[0] for word in full_list_of_regions}

    dict_of_fed_dist = {
        b_fed_dist_dal_vos: keyboard_dal_vost_reg_choice,
        b_fed_dist_privolz: keyboard_privolz_reg_choice,
        b_fed_dist_sev_kaz: keyboard_sev_kav_reg_choice,
        b_fed_dist_sev_zap: keyboard_sev_zap_reg_choice,
        b_fed_dist_sibiria: keyboard_sibiria_reg_choice,
        b_fed_dist_uralsky: keyboard_urals_reg_choice,
        b_fed_dist_central: keyboard_central_reg_choice,
        b_fed_dist_yuzhniy: keyboard_yuzhniy_reg_choice,
    }

    # Other menu
    b_view_latest_searches = 'посмотреть последние поиски'
    b_goto_community = 'написать разработчику бота'
    b_goto_first_search = 'ознакомиться с информацией для новичка'
    b_goto_photos = 'посмотреть красивые фото с поисков'
    keyboard_other = [
        [b_view_latest_searches],
        [b_goto_first_search],
        [b_goto_community],
        [b_goto_photos],
        [b_back_to_start],
    ]

    # Admin - specially keep it for Admin, regular users unlikely will be interested in it

    b_act_titles = 'названия'  # these are "Title update notification" button

    b_admin_menu = 'admin'
    b_test_menu = 'test'
    b_test_search_follow_mode_on = 'test search follow mode on'  # noqa
    b_test_search_follow_mode_off = 'test search follow mode off'

    b_pref_age_0_6_act = 'отключить: Маленькие Дети 0-6 лет'
    b_pref_age_0_6_deact = 'включить: Маленькие Дети 0-6 лет'
    b_pref_age_7_13_act = 'отключить: Подростки 7-13 лет'
    b_pref_age_7_13_deact = 'включить: Подростки 7-13 лет'
    b_pref_age_14_20_act = 'отключить: Молодежь 14-20 лет'
    b_pref_age_14_20_deact = 'включить: Молодежь 14-20 лет'
    b_pref_age_21_50_act = 'отключить: Взрослые 21-50 лет'
    b_pref_age_21_50_deact = 'включить: Взрослые 21-50 лет'
    b_pref_age_51_80_act = 'отключить: Старшее Поколение 51-80 лет'
    b_pref_age_51_80_deact = 'включить: Старшее Поколение 51-80 лет'
    b_pref_age_81_on_act = 'отключить: Старцы более 80 лет'
    b_pref_age_81_on_deact = 'включить: Старцы более 80 лет'

    b_pref_radius_act = 'включить ограничение по расстоянию'
    b_pref_radius_deact = 'отключить ограничение по расстоянию'
    b_pref_radius_change = 'изменить ограничение по расстоянию'

    b_help_yes = 'да, помогите мне настроить бот'
    b_help_no = 'нет, помощь не требуется'

    # basic markup which will be substituted for all specific cases
    reply_markup = reply_markup_main

    conn_psy = sql_connect_by_psycopg2()
    cur = conn_psy.cursor()

    logging.info(f'Before if got_message and not got_callback: {got_message=}')

    if got_message and not got_callback:
        last_inline_message_ids = get_last_user_inline_dialogue(cur, user_id)
        if last_inline_message_ids:
            for last_inline_message_id in last_inline_message_ids:
                params = {'chat_id': user_id, 'message_id': last_inline_message_id}
                make_api_call('editMessageReplyMarkup', bot_token, params, 'main() if got_message and not got_callback')
            delete_last_user_inline_dialogue(cur, user_id)

    if got_message:
        save_user_message_to_bot(cur, user_id, got_message)

    bot_request_aft_usr_msg = ''
    msg_sent_by_specific_code = False

    user_is_new = check_if_new_user(cur, user_id)
    logging.info(f'After check_if_new_user: {user_is_new=}')
    if user_is_new:
        save_new_user(user_id, username)

    onboarding_step_id, onboarding_step_name = check_onboarding_step(cur, user_id, user_is_new)
    user_regions = get_user_reg_folders_preferences(cur, user_id)
    user_role = get_user_role(cur, user_id)

    # Check what was last request from bot and if bot is expecting user's input
    bot_request_bfr_usr_msg = get_last_bot_msg(cur, user_id)

    # placeholder for the New message from bot as reply to "update". Placed here – to avoid errors of GCF
    bot_message = ''

    # ONBOARDING PHASE
    if onboarding_step_id < 80:
        onboarding_step_id = run_onboarding(user_id, username, onboarding_step_id, got_message)

    # get coordinates from the text
    if bot_request_bfr_usr_msg == 'input_of_coords_man':
        user_latitude, user_longitude = get_coordinates_from_string(got_message, user_latitude, user_longitude)

    # if there is any coordinates from user
    if user_latitude and user_longitude:
        process_user_coordinates(
            cur,
            user_id,
            user_latitude,
            user_longitude,
            b_coords_check,
            b_coords_del,
            b_back_to_start,
            bot_request_aft_usr_msg,
        )
        cur.close()
        conn_psy.close()

        return 'finished successfully. in was a message with user coordinates'

    try:
        # if there is a text message from user
        if got_message:
            # if pushed \start
            if got_message == c_start:
                if user_is_new:
                    # FIXME – 02.12.2023 – hiding menu button for the newcomers
                    #  (in the future it should be done in manage_user script)
                    method = 'setMyCommands'
                    params = {'commands': [], 'scope': {'type': 'chat', 'chat_id': user_id}}
                    response = make_api_call(
                        method=method, bot_api_token=bot_token, params=params, call_context='if user_is_new'
                    )
                    result = process_response_of_api_call(user_id, response)
                    logging.info(f'hiding user {user_id} menu status = {result}')
                    # FIXME ^^^

                    bot_message = (
                        'Привет! Это Бот Поисковика ЛизаАлерт. Он помогает Поисковикам '
                        'оперативно получать информацию о новых поисках или об изменениях '
                        'в текущих поисках.'
                        '\n\nБот управляется кнопками, которые заменяют обычную клавиатуру. '
                        'Если кнопки не отображаются, справа от поля ввода сообщения '
                        'есть специальный значок, чтобы отобразить кнопки управления ботом.'
                        '\n\nДавайте настроим бот индивидуально под вас. Пожалуйста, '
                        'укажите вашу роль сейчас?'
                    )
                    keyboard_role = [
                        [b_role_iam_la],
                        [b_role_want_to_be_la],
                        [b_role_looking_for_person],
                        [b_role_other],
                        [b_role_secret],
                    ]
                    reply_markup = ReplyKeyboardMarkup(keyboard_role, resize_keyboard=True)

                else:
                    bot_message = 'Привет! Бот управляется кнопками, которые заменяют обычную клавиатуру.'
                    reply_markup = reply_markup_main

            elif (
                onboarding_step_id == 20 and got_message in full_dict_of_regions
            ) or got_message == b_reg_moscow:  # "moscow_replied"
                # FIXME – 02.12.2023 – un-hiding menu button for the newcomers
                #  (in the future it should be done in manage_user script)
                method = 'deleteMyCommands'
                params = {'scope': {'type': 'chat', 'chat_id': user_id}}
                response = make_api_call(method=method, bot_api_token=bot_token, params=params)
                result = process_response_of_api_call(user_id, response)
                # FIXME ^^^

                bot_message = (
                    '🎉 Отлично, вы завершили базовую настройку Бота.\n\n'
                    'Список того, что сейчас умеет бот:\n'
                    '- Высылает сводку по идущим поискам\n'
                    '- Высылает сводку по последним поисками\n'
                    '- Информирует о новых поисках с указанием расстояния до поиска\n'
                    '- Информирует об изменении Статуса / Первого поста Инфорга\n'
                    '- Информирует о новых комментариях Инфорга или пользователей\n'
                    '- Позволяет гибко настроить информирование на основе удаленности от '
                    'вас, возраста пропавшего и т.п.\n\n'
                    'С этого момента вы начнёте получать основные уведомления в '
                    'рамках выбранного региона, как только появятся новые изменения. '
                    'Или же вы сразу можете просмотреть списки Активных и Последних поисков.\n\n'
                    'Бот приглашает вас настроить дополнительные параметры (можно пропустить):\n'
                    '- Настроить виды уведомлений\n'
                    '- Указать домашние координаты\n'
                    '- Указать максимальный радиус до поиска\n'
                    '- Указать возрастные группы пропавших\n'
                    '- Связать бот с Форумом\n\n'
                    'Создатели Бота надеются, что Бот сможет помочь вам в ваших задачах! Удачи!'
                )

                keyboard_role = [
                    [b_set_pref_notif_type],
                    [b_set_pref_coords],
                    [b_set_pref_radius],
                    [b_set_pref_age],
                    [b_set_forum_nick],
                    [b_view_latest_searches],
                    [b_view_act_searches],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_role, resize_keyboard=True)

                if got_message == b_reg_moscow:
                    bot_message, reply_markup = manage_if_moscow(
                        cur,
                        user_id,
                        username,
                        got_message,
                        b_reg_moscow,
                        b_reg_not_moscow,
                        reply_markup,
                        keyboard_fed_dist_set,
                        bot_message,
                        user_role,
                    )
                else:
                    save_onboarding_step(user_id, username, 'region_set')
                    save_user_pref_topic_type(cur, user_id, 'default', user_role)
                    updated_regions = update_and_download_list_of_regions(
                        cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
                    )

            elif got_message in {
                b_role_looking_for_person,
                b_role_want_to_be_la,
                b_role_iam_la,
                b_role_secret,
                b_role_other,
                b_orders_done,
                b_orders_tbd,
            }:
                # save user role & onboarding stage
                if got_message in {
                    b_role_want_to_be_la,
                    b_role_iam_la,
                    b_role_looking_for_person,
                    b_role_other,
                    b_role_secret,
                }:
                    user_role = save_user_pref_role(cur, user_id, got_message)
                    save_onboarding_step(user_id, username, 'role_set')

                # get user role = relatives looking for a person
                if got_message == b_role_looking_for_person:
                    bot_message = (
                        'Тогда вам следует:\n\n'
                        '1. Подайте заявку на поиск в ЛизаАлерт ОДНИМ ИЗ ДВУХ способов:\n'
                        '  1.1. САМОЕ БЫСТРОЕ – звоните на 88007005452 (бесплатная горячая '
                        'линия ЛизаАлерт). Вам зададут ряд вопросов, который максимально '
                        'ускорит поиск, и посоветуют дальнейшие действия. \n'
                        '  1.2. Заполните форму поиска https://lizaalert.org/zayavka-na-poisk/ \n'
                        'После заполнения формы на сайте нужно ожидать звонка от ЛизаАлерт. На '
                        'обработку может потребоваться более часа. Если нет возможности ждать, '
                        'после заполнения заявки следует позвонить на горячую линию отряда '
                        '88007005452, сообщив, что вы уже оформили заявку на сайте.\n\n'
                        '2. Подать заявление в Полицию. Если иное не посоветовали на горячей линии,'
                        'заявка в Полицию – поможет ускорить и упростить поиск. Самый быстрый '
                        'способ – позвонить на 102.\n\n'
                        '3. Отслеживайте ход поиска.\n'
                        'Когда заявки в ЛизаАлерт и Полицию сделаны, отряд начнет первые '
                        'мероприятия для поиска человека: уточнение деталей, прозвоны '
                        'в госучреждения, формирование плана и команды поиска и т.п. Весь этот'
                        'процесс вам не будет виден, но часто люди находятся именно на этой стадии'
                        'поиска. Если первые меры не помогут и отряд примет решение проводить'
                        'выезд "на место поиска" – тогда вы сможете отслеживать ход поиска '
                        'через данный Бот, для этого продолжите настройку бота: вам нужно будет'
                        'указать ваш регион и выбрать, какие уведомления от бота вы будете '
                        'получать. '
                        'Как альтернатива, вы можете зайти на форум https://lizaalert.org/forum/, '
                        'и отслеживать статус поиска там.\n'
                        'Отряд сделает всё возможное, чтобы найти вашего близкого как можно '
                        'скорее.\n\n'
                        'Сообщите, подали ли вы заявки в ЛизаАлерт и Полицию?'
                    )

                    keyboard_orders = [[b_orders_done], [b_orders_tbd]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_orders, resize_keyboard=True)

                # get user role = potential LA volunteer
                elif got_message == b_role_want_to_be_la:
                    bot_message = (
                        'Супер! \n'
                        'Знаете ли вы, как можно помогать ЛизаАлерт? Определились ли вы, как '
                        'вы готовы помочь? Если еще нет – не беда – рекомендуем '
                        'ознакомиться со статьёй: '
                        'https://takiedela.ru/news/2019/05/25/instrukciya-liza-alert/\n\n'
                        'Задачи, которые можно выполнять даже без специальной подготовки, '
                        'выполняют Поисковики "на месте поиска". Этот Бот как раз старается '
                        'помогать именно Поисковикам. '
                        'Есть хороший сайт, рассказывающий, как начать участвовать в поиске: '
                        'https://xn--b1afkdgwddgp9h.xn--p1ai/\n\n'
                        'В случае любых вопросов – не стесняйтесь, обращайтесь на общий телефон, '
                        '8 800 700-54-52, где вам помогут с любыми вопросами при вступлении в отряд.\n\n'
                        'А если вы "из мира IT" и готовы помогать развитию этого Бота,'
                        'пишите нам в специальный чат https://t.me/+2J-kV0GaCgwxY2Ni\n\n'
                        'Надеемся, эта информацию оказалась полезной. '
                        'Если вы готовы продолжить настройку Бота, уточните, пожалуйста: '
                        'ваш основной регион – это Москва и Московская Область?'
                    )
                    keyboard_coordinates_admin = [[b_reg_moscow], [b_reg_not_moscow]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                # get user role = all others
                elif got_message in {b_role_iam_la, b_role_other, b_role_secret, b_orders_done, b_orders_tbd}:
                    bot_message = (
                        'Спасибо. Теперь уточните, пожалуйста, ваш основной регион – это '
                        'Москва и Московская Область?'
                    )
                    keyboard_coordinates_admin = [[b_reg_moscow], [b_reg_not_moscow]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

            elif got_message in {b_reg_not_moscow}:
                bot_message, reply_markup = manage_if_moscow(
                    cur,
                    user_id,
                    username,
                    got_message,
                    b_reg_moscow,
                    b_reg_not_moscow,
                    reply_markup_main,
                    keyboard_fed_dist_set,
                    None,
                    user_role,
                )

            elif got_message == b_help_no:
                bot_message = (
                    'Спасибо, понятно. Мы записали. Тогда бот более не будет вас беспокоить, '
                    'пока вы сами не напишите в бот.\n\n'
                    'На прощание, бот хотел бы посоветовать следующие вещи, делающие мир лучше:\n\n'
                    '1. Посмотреть <a href="https://t.me/+6LYNNEy8BeI1NGUy">позитивные фото '
                    'с поисков ЛизаАлерт</a>.\n\n'
                    '2. <a href="https://lizaalert.org/otryadnye-nuzhdy/">Помочь '
                    'отряду ЛизаАлерт, пожертвовав оборудование для поисков людей</a>.\n\n'
                    '3. Помочь создателям данного бота, присоединившись к группе разработчиков'
                    'или оплатив облачную инфраструктуру для бесперебойной работы бота. Для этого'
                    '<a href="https://t.me/MikeMikeT">просто напишите разработчику бота</a>.\n\n'
                    'Бот еще раз хотел подчеркнуть, что как только вы напишите что-то в бот – он'
                    'сразу же "забудет", что вы ранее просили вас не беспокоить:)\n\n'
                    'Обнимаем:)'
                )
                keyboard = [[b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            elif got_message == b_help_yes:
                bot_message = (
                    'Супер! Тогда давайте посмотрим, что у вас не настроено.\n\n'
                    'У вас не настроен Регион поисков – без него Бот не может определить, '
                    'какие поиски вас интересуют. Вы можете настроить регион двумя способами:\n'
                    '1. Либо автоматически на основании ваших координат – нужно будет отправить '
                    'вашу геолокацию (работает только с мобильных устройств),\n'
                    '2. Либо выбрав регион вручную: для этого нужно сначала выбрать ФО = '
                    'Федеральный Округ, где находится ваш регион, а потом кликнуть на сам регион. '
                    '\n\n'
                )

            # set user pref: urgency
            elif got_message in {
                b_pref_urgency_highest,
                b_pref_urgency_high,
                b_pref_urgency_medium,
                b_pref_urgency_low,
            }:
                save_user_pref_urgency(
                    cur,
                    user_id,
                    got_message,
                    b_pref_urgency_highest,
                    b_pref_urgency_high,
                    b_pref_urgency_medium,
                    b_pref_urgency_low,
                )
                bot_message = 'Хорошо, спасибо. Бот запомнил ваш выбор.'

            # force user to input a region
            elif not user_regions and not (
                got_message in full_dict_of_regions
                or got_message in dict_of_fed_dist
                or got_message in {b_menu_set_region, c_start, b_settings, c_settings}
            ):
                bot_message = (
                    'Для корректной работы бота, пожалуйста, задайте свой регион. Для этого '
                    'с помощью кнопок меню выберите сначала ФО (федеральный округ), а затем и '
                    'регион. Можно выбирать несколько регионов из разных ФО. Выбор региона '
                    'также можно отменить, повторно нажав на кнопку с названием региона. '
                    'Функционал бота не будет активирован, пока не выбран хотя бы один регион.'
                )

                keyboard_coordinates_admin = [[b_menu_set_region]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                logging.info(f'user {user_id} is forced to fill in the region')

            elif got_callback and got_callback['action'] == 'search_follow_mode':  # issue#425
                bot_message, reply_markup = manage_search_whiteness(
                    cur, user_id, got_callback, callback_query_id, callback_query, bot_token
                )

            elif got_callback and got_callback['action'] in [
                'search_follow_mode_on',
                'search_follow_mode_off',
            ]:  # issue#425
                bot_message = manage_search_follow_mode(
                    cur, user_id, got_callback, callback_query_id, callback_query, bot_token
                )
                reply_markup = reply_markup_main

            # Send summaries
            elif got_message in {
                b_view_latest_searches,
                b_view_act_searches,
                c_view_latest_searches,
                c_view_act_searches,
            }:
                msg_sent_by_specific_code = True

                temp_dict = {
                    b_view_latest_searches: 'all',
                    b_view_act_searches: 'active',
                    c_view_latest_searches: 'all',
                    c_view_act_searches: 'active',
                }

                cur.execute(
                    """
                    SELECT folder_id, folder_display_name FROM geo_folders_view WHERE folder_type='searches';
                    """
                )

                folders_list = cur.fetchall()

                if get_search_follow_mode(cur, user_id):
                    # issue#425 make inline keyboard - list of searches
                    keyboard = []  # to combine monolit ikb for all user's regions
                    ikb_searches_count = 0

                    region_name = ''
                    for region in user_regions:
                        for line in folders_list:
                            if line[0] == region:
                                region_name = line[1]
                                break

                        logging.info(f'Before if region_name.find...: {bot_message=}; {keyboard=}')
                        # check if region – is an archive folder: if so – it can be sent only to 'all'
                        if region_name.find('аверш') == -1 or temp_dict[got_message] == 'all':
                            new_region_ikb_list = compose_full_message_on_list_of_searches_ikb(
                                cur, temp_dict[got_message], user_id, region, region_name
                            )
                            keyboard.append(new_region_ikb_list)
                            ikb_searches_count += len(new_region_ikb_list) - 1  ##number of searches in the region
                            logging.info(f'After += compose_full_message_on_list_of_searches_ikb: {keyboard=}')

                    ##msg_sent_by_specific_code for combined ikb start
                    if ikb_searches_count == 0:
                        bot_message = 'Незавершенные поиски в соответствии с Вашей настройкой видов поисков не найдены.'
                        params = {
                            'parse_mode': 'HTML',
                            'disable_web_page_preview': True,
                            'reply_markup': reply_markup,
                            'chat_id': user_id,
                            'text': bot_message,
                        }
                        context = f'{user_id=}, context_step=b1'
                        response = make_api_call('sendMessage', bot_token, params, context)
                        logging.info(f'{response=}; {user_id=}; context_step=b2')
                        result = process_response_of_api_call(user_id, response)
                        logging.info(f'{result=}; {user_id=}; context_step=b3')
                        inline_processing(cur, response, params)
                    else:
                        # issue#425 show the inline keyboard

                        ##TBD. May be will be useful to show quantity of marked searches
                        #                        searches_marked = 0
                        #                        for region_keyboard in keyboard:
                        #                            for ikb_line in region_keyboard:
                        #                                if ikb_line[0].get("callback_data") and not ikb_line[0]["text"][:1]=='  ':
                        #                                    searches_marked += 1

                        for i, region_keyboard in enumerate(keyboard):
                            if i == 0:
                                bot_message = """МЕНЮ АКТУАЛЬНЫХ ПОИСКОВ ДЛЯ ОТСЛЕЖИВАНИЯ.
Каждый поиск ниже дан строкой из пары кнопок: кнопка пометки для отслеживания и кнопка перехода на форум.
👀 - знак пометки поиска для отслеживания, уведомления будут приходить только по помеченным поискам. 
Если таких нет, то уведомления будут приходить по всем поискам согласно настройкам.
❌ - пометка поиска для игнорирования ("черный список") - уведомления по таким поискам не будут приходить в любом случае."""
                            else:
                                bot_message = ''

                            # Pop region caption from the region_keyboard and put it into bot-message
                            bot_message += '\n' if len(bot_message) > 0 else ''
                            bot_message += (
                                f'<a href="{region_keyboard[0][0]["url"]}">{region_keyboard[0][0]["text"]}</a>'
                            )
                            region_keyboard.pop(0)

                            if i == (len(keyboard) - 1):
                                region_keyboard += [
                                    [
                                        {
                                            'text': 'Отключить выбор поисков для отслеживания',
                                            'callback_data': '{"action":"search_follow_mode_off"}',
                                        }
                                    ]
                                ]

                            reply_markup = InlineKeyboardMarkup(region_keyboard)
                            logging.info(f'{bot_message=}; {region_keyboard=}; context_step=b00')
                            # process_sending_message_async(user_id=user_id, data=data)
                            context = f'Before if reply_markup and not isinstance(reply_markup, dict): {reply_markup=}, context_step=b01'
                            logging.info(f'{context=}: {reply_markup=}')
                            if reply_markup and not isinstance(reply_markup, dict):
                                reply_markup = reply_markup.to_dict()
                                context = (
                                    f'After reply_markup.to_dict(): {reply_markup=}; {user_id=}; context_step=b02a'
                                )
                                logging.info(f'{context=}: {reply_markup=}')

                            params = {
                                'parse_mode': 'HTML',
                                'disable_web_page_preview': True,
                                'reply_markup': reply_markup,
                                'chat_id': user_id,
                                'text': bot_message,
                            }
                            context = f'{user_id=}, context_step=b1'
                            response = make_api_call('sendMessage', bot_token, params, context)
                            logging.info(f'{response=}; {user_id=}; context_step=b2')
                            result = process_response_of_api_call(user_id, response)
                            logging.info(f'{result=}; {user_id=}; context_step=b3')
                            inline_processing(cur, response, params)
                    ##msg_sent_by_specific_code for combined ikb end

                    # saving the last message from bot
                    try:
                        cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))
                        cur.execute(
                            'INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);',
                            (user_id, datetime.datetime.now(), 'report'),
                        )
                    except Exception as e:
                        logging.info('failed to save the last message from bot')
                        logging.exception(e)

                else:
                    region_name = ''
                    for region in user_regions:
                        for line in folders_list:
                            if line[0] == region:
                                region_name = line[1]
                                break

                        # check if region – is an archive folder: if so – it can be sent only to 'all'
                        if region_name.find('аверш') == -1 or temp_dict[got_message] == 'all':
                            bot_message = compose_full_message_on_list_of_searches(
                                cur, temp_dict[got_message], user_id, region, region_name
                            )
                            reply_markup = reply_markup_main
                            data = {
                                'text': bot_message,
                                'reply_markup': reply_markup,
                                'parse_mode': 'HTML',
                                'disable_web_page_preview': True,
                            }
                            process_sending_message_async(user_id=user_id, data=data)

                            # saving the last message from bot
                            try:
                                cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))
                                cur.execute(
                                    'INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);',
                                    (user_id, datetime.datetime.now(), 'report'),
                                )
                            except Exception as e:
                                logging.info('failed to save the last message from bot')
                                logging.exception(e)
                    # issue425 Button for turn on search following mode
                    try:
                        search_follow_mode_ikb = [
                            [
                                {
                                    'text': 'Включить выбор поисков для отслеживания',
                                    'callback_data': '{"action":"search_follow_mode_on"}',
                                }
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(search_follow_mode_ikb)
                        if reply_markup and not isinstance(reply_markup, dict):
                            reply_markup = reply_markup.to_dict()
                            context = f'After reply_markup.to_dict(): {reply_markup=}; {user_id=}; context_step=a00'
                            logging.info(f'{context=}: {reply_markup=}')
                        params = {
                            'parse_mode': 'HTML',
                            'disable_web_page_preview': True,
                            'reply_markup': reply_markup,
                            'chat_id': user_id,
                            'text': """Вы можете включить возможность выбора поисков для отслеживания, 
чтобы получать уведомления не со всех актуальных поисков, 
а только с выбранных Вами.""",
                        }
                        context = f'{user_id=}, context_step=a01'
                        response = make_api_call('sendMessage', bot_token, params, context)
                        logging.info(f'{response=}; {user_id=}; context_step=a02')
                        result = process_response_of_api_call(user_id, response)
                        logging.info(f'{result=}; {user_id=}; context_step=a03')
                        inline_processing(cur, response, params)
                    except Exception as e:
                        logging.info('failed to show button for turn on search following mode')
                        logging.exception(e)

            # Perform individual replies

            # Admin mode
            elif got_message.lower() == b_admin_menu:
                bot_message = 'Вы вошли в специальный тестовый админ-раздел'

                # keyboard for Home Coordinates sharing
                keyboard_coordinates_admin = [[b_back_to_start], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

            # FIXME - WIP
            elif got_message.lower() == b_test_menu:
                add_user_sys_role(cur, user_id, 'tester')
                bot_message = (
                    'Вы в секретном тестовом разделе, где всё может работать не так :) '
                    'Если что – пишите, пожалуйста, в телеграм-чат '
                    'https://t.me/joinchat/2J-kV0GaCgwxY2Ni'
                    '\n💡 А еще Вам добавлена роль tester - некоторые тестовые функции включены автоматически.'
                    '\nДля отказа от роли tester нужно отправить команду notest'
                )
                # keyboard_coordinates_admin = [[b_set_topic_type], [b_back_to_start]]
                # [b_set_pref_urgency], [b_set_forum_nick]

                map_button = {'text': 'Открыть карту поисков', 'web_app': {'url': get_app_config().web_app_url_test}}
                keyboard = [[map_button]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            # FIXME ^^^

            elif got_message.lower() == 'notest':
                delete_user_sys_role(cur, user_id, 'tester')
                bot_message = 'Роль tester удалена. Приходите еще! :-) Возвращаемся в главное меню.'
                reply_markup = reply_markup_main

            ###            elif got_message.lower() == b_test_search_follow_mode_on: #issue425
            ###                set_search_follow_mode(cur, user_id, True)
            ###                bot_message = 'Возможность отслеживания поисков включена. Возвращаемся в главное меню.'
            ###                reply_markup = reply_markup_main

            elif got_message.lower() == b_test_search_follow_mode_off:  ##remains for some time for emrgency case
                set_search_follow_mode(cur, user_id, False)
                bot_message = 'Возможность отслеживания поисков вЫключена. Возвращаемся в главное меню.'
                reply_markup = reply_markup_main

            elif got_message in {b_map, c_map}:
                bot_message = (
                    'В Боте Поисковика теперь можно посмотреть 🗺️Карту Поисков📍.\n\n'
                    'На карте вы сможете увидеть все активные поиски, '
                    'построить к каждому из них маршрут с учетом пробок, '
                    'а также открыть этот маршрут в сервисах Яндекс.\n\n'
                    'Карта работает в тестовом режиме.\n'
                    'Если карта будет работать некорректно, или вы видите, как ее необходимо '
                    'доработать – напишите в '
                    '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">чат разработчиков</a>.'
                    ''
                )

                map_button = {'text': 'Открыть карту поисков', 'web_app': {'url': get_app_config().web_app_url}}
                keyboard = [[map_button]]
                reply_markup = InlineKeyboardMarkup(keyboard)

            elif (
                got_message == b.set.topic_type.text
                or b.topic_types.contains(got_message)
                or (got_hash and b.topic_types.contains(got_hash))
            ):  # noqa
                callback_query_message_id = callback_query.message.id if callback_query else None
                bot_message, reply_markup = manage_topic_type(
                    cur, user_id, got_message, b, got_callback, callback_query_id, bot_token, callback_query_message_id
                )

            elif got_message in {
                b_set_pref_age,
                b_pref_age_0_6_act,
                b_pref_age_0_6_deact,
                b_pref_age_7_13_act,
                b_pref_age_7_13_deact,
                b_pref_age_14_20_act,
                b_pref_age_14_20_deact,
                b_pref_age_21_50_act,
                b_pref_age_21_50_deact,
                b_pref_age_51_80_act,
                b_pref_age_51_80_deact,
                b_pref_age_81_on_act,
                b_pref_age_81_on_deact,
            }:
                input_data = None if got_message == b_set_pref_age else got_message
                keyboard, first_visit = manage_age(cur, user_id, input_data)
                keyboard.append([b_back_to_start])
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                if got_message.lower() == b_set_pref_age:
                    bot_message = (
                        'Чтобы включить или отключить уведомления по определенной возрастной '
                        'группе, нажмите на неё. Настройку можно изменить в любой момент.'
                    )
                    if first_visit:
                        bot_message = (
                            'Данное меню позволяет выбрать возрастные категории БВП '
                            '(без вести пропавших), по которым вы хотели бы получать уведомления. '
                            'Важно, что если бот не сможет распознать возраст БВП, тогда вы '
                            'всё равно получите уведомление.\nТакже данная настройка не влияет на '
                            'разделы Актуальные Поиски и Последние Поиски – в них вы всё также '
                            'сможете увидеть полный список поисков.\n\n' + bot_message
                        )
                else:
                    bot_message = 'Спасибо, записали.'

            elif (
                got_message in {b_set_pref_radius, b_pref_radius_act, b_pref_radius_deact, b_pref_radius_change}
                or bot_request_bfr_usr_msg == 'radius_input'
            ):
                bot_message, reply_markup, bot_request_aft_usr_msg = manage_radius(
                    cur,
                    user_id,
                    got_message,
                    b_set_pref_radius,
                    b_pref_radius_act,
                    b_pref_radius_deact,
                    b_pref_radius_change,
                    b_back_to_start,
                    b_set_pref_coords,
                    bot_request_bfr_usr_msg,
                )

            elif (
                got_message in {b_set_forum_nick, b_yes_its_me, b_no_its_not_me}
                or bot_request_bfr_usr_msg == 'input_of_forum_username'
            ):
                bot_message, reply_markup, bot_request_aft_usr_msg = manage_linking_to_forum(
                    cur,
                    got_message,
                    user_id,
                    b_set_forum_nick,
                    b_back_to_start,
                    bot_request_bfr_usr_msg,
                    b_admin_menu,
                    b_test_menu,
                    b_yes_its_me,
                    b_no_its_not_me,
                    b_settings,
                    reply_markup_main,
                )

            elif got_message == b_set_pref_urgency:
                bot_message = (
                    'Очень многие поисковики пользуются этим Ботом. При любой рассылке нотификаций'
                    ' Бот ставит все сообщения в очередь, и они обрабатываются '
                    'со скоростью, ограниченной технологиями Телеграма. Иногда, в случае нескольких'
                    ' больших поисков, очередь вырастает и кто-то получает сообщения практически '
                    'сразу, а кому-то они приходят с задержкой.\n'
                    'Вы можете помочь сделать рассылки уведомлений более "нацеленными", обозначив '
                    'с какой срочностью вы бы хотели получать уведомления от Бота. В скобках '
                    'указаны примерные сроки задержки относительно появления информации на форуме. '
                    'Выберите наиболее подходящий Вам вариант'
                )
                keyboard = [
                    [b_pref_urgency_highest],
                    [b_pref_urgency_high],
                    [b_pref_urgency_medium],
                    [b_pref_urgency_low],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            # DEBUG: for debugging purposes only
            elif got_message.lower() == 'go':
                publish_to_pubsub(Topics.topic_notify_admin, 'test_admin_check')

            elif got_message in {b_other, c_other}:
                bot_message = (
                    'Здесь можно посмотреть статистику по 20 последним поискам, перейти в '
                    'канал Коммъюнити или Прочитать важную информацию для Новичка и посмотреть '
                    'душевные фото с поисков'
                )
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            elif got_message in {b_menu_set_region, b_fed_dist_pick_other}:
                bot_message = update_and_download_list_of_regions(
                    cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
                )
                reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)

            elif got_message in dict_of_fed_dist:
                updated_regions = update_and_download_list_of_regions(
                    cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
                )
                bot_message = updated_regions
                reply_markup = ReplyKeyboardMarkup(dict_of_fed_dist[got_message], resize_keyboard=True)

            elif got_message in full_dict_of_regions:
                updated_regions = update_and_download_list_of_regions(
                    cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
                )
                bot_message = updated_regions
                keyboard = keyboard_fed_dist_set
                for fed_dist in dict_of_fed_dist:
                    for region in dict_of_fed_dist[fed_dist]:
                        if region[0] == got_message:
                            keyboard = dict_of_fed_dist[fed_dist]
                            break
                    else:
                        continue
                    break
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                if onboarding_step_id == 20:  # "moscow_replied"
                    save_onboarding_step(user_id, username, 'region_set')
                    save_user_pref_topic_type(cur, user_id, 'default', user_role)

            elif got_message in {b_settings, c_settings}:
                bot_message = (
                    'Это раздел с настройками. Здесь вы можете выбрать удобные для вас '
                    'уведомления, а также ввести свои "домашние координаты", на основе которых '
                    'будет рассчитываться расстояние и направление до места поиска. Вы в любой '
                    'момент сможете изменить эти настройки.'
                )

                message_prefix = compose_msg_on_user_setting_fullness(cur, user_id)
                if message_prefix:
                    bot_message = f'{bot_message}\n\n{message_prefix}'

                keyboard_settings = [
                    [b_set_pref_notif_type],
                    [b_menu_set_region],
                    [b_set_topic_type],
                    [b_set_pref_coords],
                    [b_set_pref_radius],
                    [b_set_pref_age],
                    [b_set_forum_nick],
                    [b_back_to_start],
                ]  # #AK added b_set_forum_nick for issue #6
                reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)

            elif got_message == b_set_pref_coords:
                bot_message = (
                    'АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ координат работает только для носимых устройств'
                    ' (для настольных компьютеров – НЕ работает: используйте, пожалуйста, '
                    'кнопку ручного ввода координат). '
                    'При автоматическом определении координат – нажмите на кнопку и '
                    'разрешите определить вашу текущую геопозицию. '
                    'Координаты, загруженные вручную или автоматически, будут считаться '
                    'вашим "домом", откуда будут рассчитаны расстояние и '
                    'направление до поисков.'
                )
                keyboard_coordinates_1 = [
                    [b_coords_auto_def],
                    [b_coords_man_def],
                    [b_coords_check],
                    [b_coords_del],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

            elif got_message == b_coords_del:
                delete_user_coordinates(cur, user_id)
                bot_message = (
                    'Ваши "домашние координаты" удалены. Теперь расстояние и направление '
                    'до поисков не будет отображаться.\n'
                    'Вы в любой момент можете заново ввести новые "домашние координаты". '
                    'Функция Автоматического определения координат работает только для '
                    'носимых устройств, для настольного компьютера – воспользуйтесь '
                    'ручным вводом.'
                )
                keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

            elif got_message == b_coords_man_def:
                bot_message = (
                    'Введите координаты вашего дома вручную в теле сообщения и просто '
                    'отправьте. Формат: XX.XXXХХ, XX.XXXХХ, где количество цифр после точки '
                    'может быть различным. Широта (первое число) должна быть между 30 '
                    'и 80, Долгота (второе число) – между 10 и 190.'
                )
                bot_request_aft_usr_msg = 'input_of_coords_man'
                reply_markup = ReplyKeyboardRemove()

            elif got_message == b_coords_check:
                lat, lon = show_user_coordinates(cur, user_id)
                if lat and lon:
                    bot_message = 'Ваши "домашние координаты" '
                    bot_message += generate_yandex_maps_place_link(lat, lon, 'coords')

                else:
                    bot_message = 'Ваши координаты пока не сохранены. Введите их автоматически или вручную.'

                keyboard_coordinates_1 = [
                    [b_coords_auto_def],
                    [b_coords_man_def],
                    [b_coords_check],
                    [b_coords_del],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

            elif got_message == b_back_to_start:
                bot_message = 'возвращаемся в главное меню'
                reply_markup = reply_markup_main

            elif got_message == b_goto_community:
                bot_message = (
                    'Бот можно обсудить с соотрядниками в '
                    '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате '
                    'в телеграм</a>. Там можно предложить свои идеи, указать на проблемы '
                    'и получить быструю обратную связь от разработчика.'
                )
                keyboard_other = [[b_view_latest_searches], [b_goto_first_search], [b_goto_photos], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            elif got_message == b_goto_first_search:
                bot_message = (
                    'Если вы хотите стать добровольцем ДПСО «ЛизаАлерт», пожалуйста, '
                    '<a href="https://lizaalert.org/forum/viewtopic.php?t=56934">'
                    'посетите страницу форума</a>, там можно ознакомиться с базовой информацией '
                    'для новичков и задать свои вопросы.'
                    'Если вы готовитесь к своему первому поиску – приглашаем '
                    '<a href="https://xn--b1afkdgwddgp9h.xn--p1ai/">ознакомиться с основами '
                    'работы ЛА</a>. Всю теорию работы ЛА необходимо получать от специально '
                    'обученных волонтеров ЛА. Но если у вас еще не было возможности пройти '
                    'официальное обучение, а вы уже готовы выехать на поиск – этот ресурс '
                    'для вас.'
                )
                keyboard_other = [[b_view_latest_searches], [b_goto_community], [b_goto_photos], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            elif got_message == b_goto_photos:
                bot_message = (
                    'Если вам хочется окунуться в атмосферу ПСР, приглашаем в замечательный '
                    '<a href="https://t.me/+6LYNNEy8BeI1NGUy">телеграм-канал с красивыми фото с '
                    'поисков</a>. Все фото – сделаны поисковиками во время настоящих ПСР.'
                )
                keyboard_other = [
                    [b_view_latest_searches],
                    [b_goto_community],
                    [b_goto_first_search],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            # special block for flexible menu on notification preferences
            elif got_message in {
                b_act_all,
                b_deact_all,
                b_act_new_search,
                b_act_stat_change,
                b_act_titles,
                b_act_all_comments,
                b_set_pref_notif_type,
                b_deact_stat_change,
                b_deact_all_comments,
                b_deact_new_search,
                b_act_inforg_com,
                b_deact_inforg_com,
                b_act_field_trips_new,
                b_deact_field_trips_new,
                b_act_field_trips_change,
                b_deact_field_trips_change,
                b_act_coords_change,
                b_deact_coords_change,
                b_act_first_post_change,
                b_deact_first_post_change,
            }:
                # save preference for +ALL
                if got_message == b_act_all:
                    bot_message = (
                        'Супер! теперь вы будете получать уведомления в телеграм в случаях: '
                        'появление нового поиска, изменение статуса поиска (стоп, НЖ, НП), '
                        'появление новых комментариев по всем поискам. Вы в любой момент '
                        'можете изменить список уведомлений'
                    )
                    save_preference(cur, user_id, 'all')

                # save preference for -ALL
                elif got_message == b_deact_all:
                    bot_message = 'Вы можете настроить типы получаемых уведомлений более гибко'
                    save_preference(cur, user_id, '-all')

                # save preference for +NEW SEARCHES
                elif got_message == b_act_new_search:
                    bot_message = (
                        'Отлично! Теперь вы будете получать уведомления в телеграм при '
                        'появлении нового поиска. Вы в любой момент можете изменить '
                        'список уведомлений'
                    )
                    save_preference(cur, user_id, 'new_searches')

                # save preference for -NEW SEARCHES
                elif got_message == b_deact_new_search:
                    bot_message = 'Записали'
                    save_preference(cur, user_id, '-new_searches')

                # save preference for +STATUS UPDATES
                elif got_message == b_act_stat_change:
                    bot_message = (
                        'Отлично! теперь вы будете получать уведомления в телеграм при '
                        'изменении статуса поисков (НЖ, НП, СТОП и т.п.). Вы в любой момент '
                        'можете изменить список уведомлений'
                    )
                    save_preference(cur, user_id, 'status_changes')

                # save preference for -STATUS UPDATES
                elif got_message == b_deact_stat_change:
                    bot_message = 'Записали'
                    save_preference(cur, user_id, '-status_changes')

                # save preference for TITLE UPDATES
                elif got_message == b_act_titles:
                    bot_message = 'Отлично!'
                    save_preference(cur, user_id, 'title_changes')

                # save preference for +COMMENTS
                elif got_message == b_act_all_comments:
                    bot_message = (
                        'Отлично! Теперь все новые комментарии будут у вас! Вы в любой момент '
                        'можете изменить список уведомлений'
                    )
                    save_preference(cur, user_id, 'comments_changes')

                # save preference for -COMMENTS
                elif got_message == b_deact_all_comments:
                    bot_message = (
                        'Записали. Мы только оставили вам включенными уведомления о '
                        'комментариях Инфорга. Их тоже можно отключить'
                    )
                    save_preference(cur, user_id, '-comments_changes')

                # save preference for +InforgComments
                elif got_message == b_act_inforg_com:
                    bot_message = (
                        'Если вы не подписаны на уведомления по всем комментариям, то теперь '
                        'вы будете получать уведомления о комментариях от Инфорга. Если же вы '
                        'уже подписаны на все комментарии – то всё остаётся без изменений: бот '
                        'уведомит вас по всем комментариям, включая от Инфорга'
                    )
                    save_preference(cur, user_id, 'inforg_comments')

                # save preference for -InforgComments
                elif got_message == b_deact_inforg_com:
                    bot_message = 'Вы отписались от уведомлений по новым комментариям от Инфорга'
                    save_preference(cur, user_id, '-inforg_comments')

                # save preference for +FieldTripsNew
                elif got_message == b_act_field_trips_new:
                    bot_message = (
                        'Теперь вы будете получать уведомления о новых выездах по уже идущим '
                        'поискам. Обратите внимание, что это не рассылка по новым темам на '
                        'форуме, а именно о том, что в существующей теме в ПЕРВОМ посте '
                        'появилась информация о новом выезде'
                    )
                    save_preference(cur, user_id, 'field_trips_new')

                # save preference for -FieldTripsNew
                elif got_message == b_deact_field_trips_new:
                    bot_message = 'Вы отписались от уведомлений по новым выездам'
                    save_preference(cur, user_id, '-field_trips_new')

                # save preference for +FieldTripsChange
                elif got_message == b_act_field_trips_change:
                    bot_message = (
                        'Теперь вы будете получать уведомления о ключевых изменениях при '
                        'выездах, в т.ч. изменение или завершение выезда. Обратите внимание, '
                        'что эта рассылка отражает изменения только в ПЕРВОМ посте поиска.'
                    )
                    save_preference(cur, user_id, 'field_trips_change')

                # save preference for -FieldTripsChange
                elif got_message == b_deact_field_trips_change:
                    bot_message = 'Вы отписались от уведомлений по изменениям выездов'
                    save_preference(cur, user_id, '-field_trips_change')

                # save preference for +CoordsChange
                elif got_message == b_act_coords_change:
                    bot_message = (
                        'Если у штаба поменяются координаты (и об этом будет написано в первом '
                        'посте на форуме) – бот уведомит вас об этом'
                    )
                    save_preference(cur, user_id, 'coords_change')

                # save preference for -CoordsChange
                elif got_message == b_deact_coords_change:
                    bot_message = 'Вы отписались от уведомлений о смене места (координат) штаба'
                    save_preference(cur, user_id, '-coords_change')

                # save preference for -FirstPostChanges
                elif got_message == b_act_first_post_change:
                    bot_message = (
                        'Теперь вы будете получать уведомления о важных изменениях в Первом Посте'
                        ' Инфорга, где обозначено описание каждого поиска'
                    )
                    save_preference(cur, user_id, 'first_post_changes')

                # save preference for -FirstPostChanges
                elif got_message == b_deact_first_post_change:
                    bot_message = (
                        'Вы отписались от уведомлений о важных изменениях в Первом Посте'
                        ' Инфорга c описанием каждого поиска'
                    )
                    save_preference(cur, user_id, '-first_post_changes')

                # GET what are preferences
                elif got_message == b_set_pref_notif_type:
                    prefs = compose_user_preferences_message(cur, user_id)
                    if prefs[0] == 'пока нет включенных уведомлений' or prefs[0] == 'неизвестная настройка':
                        bot_message = 'Выберите, какие уведомления вы бы хотели получать'
                    else:
                        bot_message = 'Сейчас у вас включены следующие виды уведомлений:\n'
                        bot_message += prefs[0]

                else:
                    bot_message = 'empty message'

                if got_message == b_act_all:
                    keyboard_notifications_flexible = [[b_deact_all], [b_back_to_start]]
                elif got_message == b_deact_all:
                    keyboard_notifications_flexible = [
                        [b_act_all],
                        [b_deact_new_search],
                        [b_deact_stat_change],
                        [b_act_all_comments],
                        [b_deact_inforg_com],
                        [b_deact_first_post_change],
                        [b_back_to_start],
                    ]
                else:
                    # getting the list of user notification preferences
                    prefs = compose_user_preferences_message(cur, user_id)
                    keyboard_notifications_flexible = [
                        [b_act_all],
                        [b_act_new_search],
                        [b_act_stat_change],
                        [b_act_all_comments],
                        [b_act_inforg_com],
                        [b_act_first_post_change],
                        [b_back_to_start],
                    ]

                    for line in prefs[1]:
                        if line == 'all':
                            keyboard_notifications_flexible = [[b_deact_all], [b_back_to_start]]
                        elif line == 'new_searches':
                            keyboard_notifications_flexible[1] = [b_deact_new_search]
                        elif line == 'status_changes':
                            keyboard_notifications_flexible[2] = [b_deact_stat_change]
                        elif line == 'comments_changes':
                            keyboard_notifications_flexible[3] = [b_deact_all_comments]
                        elif line == 'inforg_comments':
                            keyboard_notifications_flexible[4] = [b_deact_inforg_com]
                        elif line == 'first_post_changes':
                            keyboard_notifications_flexible[5] = [b_deact_first_post_change]

                reply_markup = ReplyKeyboardMarkup(keyboard_notifications_flexible, resize_keyboard=True)

            # in case of other user messages:
            else:
                # If command in unknown
                bot_message = (
                    'не понимаю такой команды, пожалуйста, используйте кнопки со стандартными ' 'командами ниже'
                )
                reply_markup = reply_markup_main

            if not msg_sent_by_specific_code:
                # FIXME – 17.11.2023 – migrating from async to pure api call
                """
                admin_id = get_app_config().my_telegram_id
                if user_id != admin_id:
                    data = {'text': bot_message, 'reply_markup': reply_markup,
                            'parse_mode': 'HTML', 'disable_web_page_preview': True}
                    process_sending_message_async(user_id=user_id, data=data)
                else:"""

                context_step = '01a1'
                context = f'if reply_markup and not isinstance(reply_markup, dict): {reply_markup=}, {context_step=}'
                logging.info(f'{context=}: {reply_markup=}')
                if reply_markup and not isinstance(reply_markup, dict):
                    reply_markup = reply_markup.to_dict()
                    context_step = '02a1'
                    context = f'After reply_markup.to_dict(): {reply_markup=}, {context_step=}'
                    logging.info(f'{context=}: {reply_markup=}')

                if got_hash and got_callback and got_callback['action'] != 'about':
                    user_used_inline_button = True
                else:
                    user_used_inline_button = False

                if user_used_inline_button:
                    # call editMessageText to edit inline keyboard
                    # in the message where inline button was pushed
                    last_user_message_id = callback_query.message.id  ##was get_last_user_inline_dialogue(cur, user_id)
                    logging.info(f'{last_user_message_id=}')
                    # params['message_id'] = last_user_message_id
                    params = {
                        'chat_id': user_id,
                        'text': bot_message,
                        'message_id': last_user_message_id,
                        'reply_markup': reply_markup,
                    }
                    context_step = '1a1'
                    context = f'main() if user_used_inline_button: {user_id=}, {context_step=}'
                    response = make_api_call('editMessageText', bot_token, params, context)
                    context_step = '1a2'
                    context = f'main() if user_used_inline_button: {user_id=}, {context_step=}'
                    logging.info(f'{response=}; {context=}')

                else:
                    params = {
                        'parse_mode': 'HTML',
                        'disable_web_page_preview': True,
                        'reply_markup': reply_markup,
                        'chat_id': user_id,
                        'text': bot_message,
                    }
                    context_step = '1b1'
                    context = f'main() if user_used_inline_button: else: {user_id=}, {context_step=}'
                    response = make_api_call('sendMessage', bot_token, params, context)
                    context_step = '1b2'
                    context = f'main() if user_used_inline_button: else: {user_id=}, {context_step=}'
                    logging.info(f'{response=}; {context=}')

                context_step = '2'
                context = f'main() after if user_used_inline_button: {user_id=}, {context_step=}'
                logging.info(f'{response=}; {context=}')
                context_step = '3'
                context = f'main() after if user_used_inline_button: {user_id=}, {context_step=}'
                result = process_response_of_api_call(user_id, response)
                inline_processing(cur, response, params)

                logging.info(f'RESPONSE {response}')
                logging.info(f'RESULT {result}')
                # FIXME ^^^

            # saving the last message from bot
            if not bot_request_aft_usr_msg:
                bot_request_aft_usr_msg = 'not_defined'

            try:
                cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))

                cur.execute(
                    """
                    INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);
                    """,
                    (user_id, datetime.datetime.now(), bot_request_aft_usr_msg),
                )

            except Exception as e:
                logging.info(f'failed updates of table msg_from_bot for user={user_id}')
                logging.exception(e)

        # all other cases when bot was not able to understand the message from user
        else:
            logging.info('DBG.C.6. THERE IS a COMM SCRIPT INVOCATION w/O MESSAGE:')
            logging.info(str(update))
            text_for_admin = (
                f'[comm]: Empty message in Comm, user={user_id}, username={username}, '
                f'got_message={got_message}, update={update}, '
                f'bot_request_bfr_usr_msg={bot_request_bfr_usr_msg}'
            )
            logging.info(text_for_admin)
            notify_admin(text_for_admin)

    except Exception as e:
        logging.info('GENERAL COMM CRASH:')
        logging.exception(e)
        notify_admin('[comm] general script fail')

    if bot_message:
        save_bot_reply_to_user(cur, user_id, bot_message)

    cur.close()
    conn_psy.close()

    return 'finished successfully. in was a regular conversational message'
