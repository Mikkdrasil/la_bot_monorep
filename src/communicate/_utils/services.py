import asyncio
import datetime
import json
import logging
import re
import urllib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from psycopg2.extensions import cursor
from requests.models import Response
from telegram import CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, TelegramObject
from telegram.ext import Application, ContextTypes

from _dependencies.commons import Topics, get_app_config, publish_to_pubsub
from _dependencies.misc import age_writer, notify_admin, process_sending_message_async, time_counter_since_search_start
from communicate._utils.buttons import AllButtons, search_button_row_ikb
from communicate._utils.database import (
    check_if_user_has_no_regions,
    check_saved_topic_types,
    compose_msg_on_all_last_searches,
    delete_topic_type,
    distance_to_search,
    generate_yandex_maps_place_link,
    get_last_user_inline_dialogue,
    record_topic_type,
    save_bot_reply_to_user,
    save_last_user_inline_dialogue,
    save_user_coordinates,
    save_user_pref_topic_type,
    set_search_follow_mode,
)
from communicate._utils.schemas import SearchSummary


def process_block_unblock_user(user_id, user_new_status):
    """processing of system message on user action to block/unblock the bot"""

    try:
        status_dict = {'kicked': 'block_user', 'member': 'unblock_user'}

        # mark user as blocked / unblocked in psql
        message_for_pubsub = {'action': status_dict[user_new_status], 'info': {'user': user_id}}
        publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)

        if user_new_status == 'member':
            bot_message = (
                'С возвращением! Бот скучал:) Жаль, что вы долго не заходили. '
                'Мы постарались сохранить все ваши настройки с вашего прошлого визита. '
                'Если у вас есть трудности в работе бота или пожелания, как сделать бот '
                'удобнее – напишите, пожалуйста, свои мысли в'
                '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальный Чат'
                'в телеграм</a>. Спасибо:)'
            )

            keyboard_main = [['посмотреть актуальные поиски'], ['настроить бот'], ['другие возможности']]
            reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)

            data = {
                'text': bot_message,
                'reply_markup': reply_markup,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            }
            process_sending_message_async(user_id=user_id, data=data)

    except Exception as e:
        logging.info('Error in finding basic data for block/unblock user in Communicate script')
        logging.exception(e)

    return None


def save_onboarding_step(user_id: str, username: str, step: str) -> None:
    """save the certain step in onboarding"""

    # to avoid eval errors in recipient script
    if not username:
        username = 'unknown'

    message_for_pubsub = {
        'action': 'update_onboarding',
        'info': {'user': user_id, 'username': username},
        'time': str(datetime.datetime.now()),
        'step': step,
    }
    publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)

    return None


def manage_age(cur: cursor, user_id: int, user_input: Optional[str]) -> None:
    """Save user Age preference and generate the list of updated Are preferences"""

    @dataclass
    class AgePeriod:
        description: str
        name: str
        min_age: int
        max_age: int
        order: int
        current: bool = False

    age_list = [
        AgePeriod(description='Маленькие Дети 0-6 лет', name='0-6', min_age=0, max_age=6, order=0),
        AgePeriod(description='Подростки 7-13 лет', name='7-13', min_age=7, max_age=13, order=1),
        AgePeriod(description='Молодежь 14-20 лет', name='14-20', min_age=14, max_age=20, order=2),
        AgePeriod(description='Взрослые 21-50 лет', name='21-50', min_age=21, max_age=50, order=3),
        AgePeriod(description='Старшее Поколение 51-80 лет', name='51-80', min_age=51, max_age=80, order=4),
        AgePeriod(description='Старцы более 80 лет', name='80-on', min_age=80, max_age=120, order=5),
    ]

    if user_input:
        user_want_activate = True if re.search(r'(?i)включить', user_input) else False
        user_new_setting = re.sub(r'.*чить: ', '', user_input)

        chosen_setting = None
        for line in age_list:
            if user_new_setting == line.description:
                chosen_setting = line
                break

        if user_want_activate:
            cur.execute(
                """INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max) 
                        values (%s, %s, %s, %s, %s) ON CONFLICT (user_id, period_min, period_max) DO NOTHING;""",
                (user_id, chosen_setting.name, datetime.datetime.now(), chosen_setting.min_age, chosen_setting.max_age),
            )
        else:
            cur.execute(
                """DELETE FROM user_pref_age WHERE user_id=%s AND period_min=%s AND period_max=%s;""",
                (user_id, chosen_setting.min_age, chosen_setting.max_age),
            )

    # Block for Generating a list of Buttons
    cur.execute("""SELECT period_min, period_max FROM user_pref_age WHERE user_id=%s;""", (user_id,))
    raw_list_of_periods = cur.fetchall()
    first_visit = False

    if raw_list_of_periods and str(raw_list_of_periods) != 'None':
        for line_raw in raw_list_of_periods:
            got_min, got_max = int(list(line_raw)[0]), int(list(line_raw)[1])
            for line_a in age_list:
                if int(line_a.min_age) == got_min and int(line_a.max_age) == got_max:
                    line_a.current = True
    else:
        first_visit = True
        for line_a in age_list:
            line_a.current = True
        for line in age_list:
            cur.execute(
                """INSERT INTO user_pref_age (user_id, period_name, period_set_date, period_min, period_max) 
                        values (%s, %s, %s, %s, %s) ON CONFLICT (user_id, period_min, period_max) DO NOTHING;""",
                (user_id, line.name, datetime.datetime.now(), line.min_age, line.max_age),
            )

    list_of_buttons = []
    for line in age_list:
        if line.current:
            list_of_buttons.append([f'отключить: {line.description}'])
        else:
            list_of_buttons.append([f'включить: {line.description}'])

    return list_of_buttons, first_visit


def manage_radius(
    cur: cursor,
    user_id: int,
    user_input: str,
    b_menu: str,
    b_act: str,
    b_deact: str,
    b_change: str,
    b_back: str,
    b_home_coord: str,
    expect_before: str,
) -> Tuple[str, ReplyKeyboardMarkup, None]:
    """Save user Radius preference and generate the actual radius preference"""

    def check_saved_radius(user: int) -> Optional[Any]:
        """check if user already has a radius preference"""

        saved_rad = None
        cur.execute("""SELECT radius FROM user_pref_radius WHERE user_id=%s;""", (user,))
        raw_radius = cur.fetchone()
        if raw_radius and str(raw_radius) != 'None':
            saved_rad = int(raw_radius[0])
        return saved_rad

    list_of_buttons = []
    expect_after = None
    bot_message = None
    reply_markup_needed = True

    if user_input:
        if user_input.lower() == b_menu:
            saved_radius = check_saved_radius(user_id)
            if saved_radius:
                list_of_buttons = [[b_change], [b_deact], [b_home_coord], [b_back]]
                bot_message = (
                    f'Сейчас вами установлено ограничение радиуса {saved_radius} км. '
                    f'Вы в любой момент можете изменить или снять это ограничение.\n\n'
                    'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым '
                    'Бот не смог распознать никакие координаты.\n\n'
                    'Также, бот в первую очередь '
                    'проверяет расстояние от штаба, а если он не указан, то до ближайшего '
                    'населенного пункта (или топонима), указанного в теме поиска. '
                    'Расстояние считается по прямой.'
                )
            else:
                list_of_buttons = [[b_act], [b_home_coord], [b_back]]
                bot_message = (
                    'Данная настройка позволяет вам ограничить уведомления от бота только теми поисками, '
                    'для которых расстояние от ваших "домашних координат" до штаба/города '
                    'не превышает указанного вами Радиуса.\n\n'
                    'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым '
                    'Бот не смог распознать никакие координаты.\n\n'
                    'Также, Бот в первую очередь '
                    'проверяет расстояние от штаба, а если он не указан, то до ближайшего '
                    'населенного пункта (или топонима), указанного в теме поиска. '
                    'Расстояние считается по прямой.'
                )

        elif user_input in {b_act, b_change}:
            expect_after = 'radius_input'
            reply_markup_needed = False
            saved_radius = check_saved_radius(user_id)
            if saved_radius:
                bot_message = (
                    f'У вас установлено максимальное расстояние до поиска {saved_radius}.'
                    f'\n\nВведите обновлённое расстояние в километрах по прямой в формате простого '
                    f'числа (например: 150) и нажмите обычную кнопку отправки сообщения'
                )
            else:
                bot_message = (
                    'Введите расстояние в километрах по прямой в формате простого числа '
                    '(например: 150) и нажмите обычную кнопку отправки сообщения'
                )

        elif user_input == b_deact:
            list_of_buttons = [[b_act], [b_menu], [b_back]]
            cur.execute("""DELETE FROM user_pref_radius WHERE user_id=%s;""", (user_id,))
            bot_message = 'Ограничение на расстояние по поискам снято!'

        elif expect_before == 'radius_input':
            number = re.search(r'[0-9]{1,6}', str(user_input))
            if number:
                number = int(number.group())
            if number and number > 0:
                cur.execute(
                    """INSERT INTO user_pref_radius (user_id, radius) 
                               VALUES (%s, %s) ON CONFLICT (user_id) DO
                               UPDATE SET radius=%s;""",
                    (user_id, number, number),
                )
                saved_radius = check_saved_radius(user_id)
                bot_message = (
                    f'Сохранили! Теперь поиски, у которых расстояние до штаба, '
                    f'либо до ближайшего населенного пункта (топонима) превосходит '
                    f'{saved_radius} км по прямой, не будут вас больше беспокоить. '
                    f'Настройку можно изменить в любое время.'
                )
                list_of_buttons = [[b_change], [b_deact], [b_menu], [b_back]]
            else:
                bot_message = 'Не могу разобрать цифры. Давайте еще раз попробуем?'
                list_of_buttons = [[b_act], [b_menu], [b_back]]

    if reply_markup_needed:
        reply_markup = ReplyKeyboardMarkup(list_of_buttons, resize_keyboard=True)
    else:
        reply_markup = ReplyKeyboardRemove()

    return bot_message, reply_markup, expect_after


def if_user_enables(callback: Dict) -> Union[None, bool]:
    """check if user wants to enable or disable a feature"""
    user_wants_to_enable = None

    if callback['action'] == 'on':
        user_wants_to_enable = True
    elif callback['action'] == 'off':
        user_wants_to_enable = False

    return user_wants_to_enable


def make_api_call(method: str, bot_api_token: str, params: dict, call_context='') -> Union[requests.Response, None]:
    """make an API call to telegram"""

    if not params or not bot_api_token or not method:
        logging.warning(
            f'not params or not bot_api_token or not method: {method=}; {len(bot_api_token)=}; {len(params)=}'
        )
        return None

    if 'chat_id' not in params.keys() and ('scope' not in params.keys() or 'chat_id' not in params['scope'].keys()):
        return None

    url = f'https://api.telegram.org/bot{bot_api_token}/{method}'  # e.g. sendMessage
    headers = {'Content-Type': 'application/json'}

    if 'reply_markup' in params and isinstance(params['reply_markup'], TelegramObject):
        params['reply_markup'] = params['reply_markup'].to_dict()
    logging.info(f'({method=}, {call_context=})..before json_params = json.dumps(params) {params=}; {type(params)=}')
    json_params = json.dumps(params)
    logging.info(f'({method=}, {call_context=})..after json.dumps(params): {json_params=}; {type(json_params)=}')

    with requests.Session() as session:
        try:
            response = session.post(url=url, data=json_params, headers=headers)
            logging.info(f'After session.post: {response=}; {call_context=}')
        except Exception as e:
            response = None
            logging.info('Error in getting response from Telegram')
            logging.exception(e)

    logging.info(f'Before return: {response=}; {call_context=}')
    return response


def process_response_of_api_call(user_id: int, response: Response, call_context: str = '') -> str:
    """process response received as a result of Telegram API call while sending message/location"""

    try:
        if 'ok' not in response.json():
            notify_admin(f'ALARM! "ok" is not in response: {response.json()}, user {user_id}')
            return 'failed'

        if response.ok:
            logging.info(f'message to {user_id} was successfully sent')
            return 'completed'

        elif response.status_code == 400:  # Bad Request
            logging.info(f'Bad Request: message to {user_id} was not sent, {response.json()=}')
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
            return 'failed_flood_control'

        # issue425 if not response moved here from the 1st place because it reacted even on response 400
        elif not response:
            logging.info(f'response is None for {user_id=}; {call_context=}')
            return 'failed'

        else:
            logging.info(f'UNKNOWN ERROR: message to {user_id} was not sent, {response.reason=}')
            logging.exception('UNKNOWN ERROR')
            return 'cancelled'

    except Exception as e:
        logging.info('Response is corrupted')
        logging.exception(e)
        logging.info(f'{response.json()=}')
        return 'failed'


def send_callback_answer_to_api(bot_token: str, callback_query_id: str, message: str) -> str:
    """send a notification when inline button is pushed directly to Telegram API w/o any wrappers ar libraries"""

    try:
        # NB! only 200 characters
        message = message[:200]
        message_encoded = f'&text={urllib.parse.quote(message)}'

        request_text = (
            f'https://api.telegram.org/bot{bot_token}/answerCallbackQuery?callback_query_id='
            f'{callback_query_id}{message_encoded}'
        )

        with requests.Session() as session:
            response = session.get(request_text)
            logging.info(f'send_callback_answer_to_api..{response.json()=}')

    except Exception as e:
        logging.exception(e)
        logging.info('Error in getting response from Telegram')
        response = None

    result = process_response_of_api_call(callback_query_id, response)

    return result


def manage_topic_type(
    cur: cursor,
    user_id: int,
    user_input: str,
    b: AllButtons,
    user_callback: dict,
    callback_id: str,
    bot_token: str,
    callback_query_msg_id: str,
) -> Union[tuple[None, None], tuple[str, ReplyKeyboardMarkup]]:
    """Save user Topic Type preference and generate the actual topic type preference message"""

    if not user_input:
        return None, None

    list_of_current_setting_ids = check_saved_topic_types(cur, user_id)

    welcome_message = (
        'Вы можете выбрать и в любой момент поменять, по каким типам поисков или '
        'мероприятий бот должен присылать уведомления.'
    )

    # when user push "ABOUT" button
    if user_callback and user_callback['action'] == 'about':
        # this scenario assumes three steps: 1. send the "ABOUT" message, 2. delete prev MENU message 3. send NEW MENU
        about_text = (
            'ЛизаАлерт проводит несколько типов поисковых мероприятий. В Боте доступны следующие из '
            'них:\n\n'
            '• <b>Стандартные активные поиски</b> – это самые частые поиски: потерялся человек, нужно его '
            'найти, чаще всего на местности. 90% всех поисков попадают в эту категорию.\n'
            '• <b>Резонансные поиски</b> (или "Резонансы") – это срочные поиски федерального масштаба. '
            'На такие поиски призываются поисковики из разных регионов.\n'
            '• <b>Информационная поддержка</b> – это поиски, когда не требуется выезд на поисковые '
            'мероприятия, а лишь требуют помощи в распространении информации о пропавшем в в соц сетях.\n'
            '• <b>Обратные поиски</b> (поиски родных) – бывает, что находят людей, которые не могут '
            'сообщить, кто они, где они живут (потеря памяти). В таких случаях требуется поиск '
            'родственников.\n'
            '• <b>Учебные поиски</b> – это важные поиски, которые созданы ЛизаАлерт, максимально приближены'
            'по условиям к реальным поискам на местности и призваны отрабатывать навыки поиска и спасения'
            'людей в реальных условиях. Создатели бота очень рекомендуют участвовать в '
            'Учебных поисках, чтобы повышать свои навыки как поисковика.\n'
            '• <b>Ночной патруль</b> – в некоторых регионах проводятся ночные патрули в парках и других '
            'общественных зонах.\n'
            '• <b>Мероприятия</b> – это различные встречи, проводимые отрядами ЛизаАлерт. Тематика и '
            'календарь проведения сильно варьируются от региона к региону. Рекомендуем подписаться, '
            'чтобы быть в курсе всех событий в отряде вашего региона. 💡'
        )
        about_params = {'chat_id': user_id, 'text': about_text, 'parse_mode': 'HTML'}
        make_api_call('sendMessage', bot_token, about_params, "main() if ... user_callback['action'] == 'about'")
        del_message_id = callback_query_msg_id  ###was get_last_user_inline_dialogue(cur, user_id)
        if del_message_id:
            del_params = {'chat_id': user_id, 'message_id': del_message_id}
            make_api_call('deleteMessage', bot_token, del_params)
            user_input = b.set.topic_type.text  # to re-establish menu sending
            welcome_message = f'⬆️ Справка приведена выше. \n\n{welcome_message}'

    # when user just enters the MENU for topic types
    if user_input == b.set.topic_type.text:
        bot_message = welcome_message
        list_of_ids_to_change_now = []

    # when user pushed INLINE BUTTON for topic type
    else:
        topic_id = b.topic_types.button_by_hash(user_callback['hash']).id
        list_of_ids_to_change_now = [topic_id]
        user_wants_to_enable = if_user_enables(user_callback)
        if user_wants_to_enable is None:
            bot_message = ''
            pass
        elif user_wants_to_enable is True:  # not a poor design – function can be: None, True, False   # noqa
            bot_message = 'Супер, мы включили эти уведомления'
            send_callback_answer_to_api(bot_token, callback_id, bot_message)
            record_topic_type(cur, user_id, topic_id)
        else:  # user_wants_to_enable == False:  # not a poor design – function can be: None, True, False # noqa
            if len(list_of_current_setting_ids) == 1:
                bot_message = '❌ Необходима как минимум одна настройка'
                list_of_ids_to_change_now = []
                send_callback_answer_to_api(bot_token, callback_id, bot_message)
            else:
                bot_message = 'Хорошо, мы изменили список настроек'
                send_callback_answer_to_api(bot_token, callback_id, bot_message)
                delete_topic_type(cur, user_id, topic_id)

    keyboard = b.topic_types.keyboard(act_list=list_of_current_setting_ids, change_list=list_of_ids_to_change_now)
    reply_markup = InlineKeyboardMarkup(keyboard)

    logging.info(f'{list_of_current_setting_ids=}')
    logging.info(f'{user_input=}')
    logging.info(f'{list_of_ids_to_change_now=}')
    logging.info(f'{keyboard=}')

    if user_input != b.set.topic_type.text:
        bot_message = welcome_message

    return bot_message, reply_markup


def manage_search_whiteness(
    cur: cursor, user_id: int, user_callback: dict, callback_id: str, callback_query: CallbackQuery, bot_token: str
) -> Union[tuple[None, None], tuple[str, ReplyKeyboardMarkup]]:
    """Saves search_whiteness (accordingly to user's choice of search to follow) and regenerates the search list keyboard"""

    ################# ToDo further: modify select in compose_notifications

    def record_search_whiteness(user: int, search_id: int, new_mark_value) -> None:
        """Save a certain user_pref_search_whitelist for a certain user_id into the DB"""
        if new_mark_value in ['👀 ', '❌ ']:
            cur.execute(
                """INSERT INTO user_pref_search_whitelist (user_id, search_id, timestamp, search_following_mode) 
                            VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, search_id) DO UPDATE SET timestamp=%s, search_following_mode=%s;""",
                (user, search_id, datetime.datetime.now(), new_mark_value, datetime.datetime.now(), new_mark_value),
            )
        else:
            cur.execute(
                """DELETE FROM user_pref_search_whitelist WHERE user_id=%(user)s and search_id=%(search_id)s;""",
                {'user': user, 'search_id': search_id},
            )
        return None

    logging.info('callback_query=' + str(callback_query))
    logging.info(f'{user_id=}')
    # when user pushed INLINE BUTTON for topic following
    if user_callback and user_callback['action'] == 'search_follow_mode':
        # get inline keyboard from previous message to upadate it
        reply_markup = callback_query.message.reply_markup
        if reply_markup and not isinstance(reply_markup, dict):
            ikb = reply_markup.to_dict()['inline_keyboard']
        else:
            ikb = callback_query.message.reply_markup.inline_keyboard

        new_ikb = []
        logging.info(f'before for index, ikb_row in enumerate(ikb): {ikb=}')
        for index, ikb_row in enumerate(ikb):
            new_ikb += [ikb_row]
            logging.info(f'{ikb_row=}')
            if ikb_row[0].get('callback_data'):
                button_data = eval(ikb_row[0]['callback_data'])
                # Check if the pushed button matches the one in the callback
                if button_data.get('hash') and int(button_data['hash']) == int(user_callback['hash']):
                    pushed_row_index = index

        logging.info(f'before ikb_row = ikb[pushed_row_index]: {new_ikb=}')
        ikb_row = ikb[pushed_row_index]
        old_mark_value = ikb_row[0]['text'][:2]
        if old_mark_value == '  ':
            new_mark_value = '👀 '
            bot_message = 'Поиск добавлен в белый список.'
        elif old_mark_value == '👀 ':
            new_mark_value = '❌ '
            bot_message = 'Поиск добавлен в черный список.'
        else:
            new_mark_value = '  '
            bot_message = 'Пометка снята.'
        logging.info(f'before assign new_mark_value: {pushed_row_index=}, {old_mark_value=}, {new_mark_value=}')
        new_ikb[pushed_row_index][0]['text'] = new_mark_value + new_ikb[pushed_row_index][0]['text'][2:]
        # Update the search 'whiteness' (tracking state)
        record_search_whiteness(user_id, int(user_callback['hash']), new_mark_value)
        logging.info(f'before send_callback_answer_to_api: {new_ikb=}')
        send_callback_answer_to_api(bot_token, callback_id, bot_message)
        reply_markup = InlineKeyboardMarkup(new_ikb)
        logging.info(f'before api_callback_edit_inline_keyboard: {reply_markup=}')
        #        if pushed_row_index %2 ==0:##redundant because there is if user_used_inline_button
        #            api_callback_edit_inline_keyboard(bot_token, callback_query, reply_markup, user_id)

        bot_message = callback_query.message.text
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
