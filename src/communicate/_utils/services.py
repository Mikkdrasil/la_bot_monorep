import datetime
import json
import logging
import re
import urllib
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

import requests
from psycopg2.extensions import cursor
from requests.models import Response
from telegram import CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, TelegramObject

from _dependencies.commons import Topics, publish_to_pubsub
from _dependencies.misc import notify_admin, process_sending_message_async
from communicate._utils.buttons import AllButtons
from communicate._utils.database import check_saved_topic_types, delete_topic_type, record_topic_type


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
