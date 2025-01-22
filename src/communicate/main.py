# ToDo later: user_callback["action"] == "search_follow_mode" заменить на "sfmw", "sfmb"

"""receives telegram messages from users, acts accordingly and sends back the reply"""

import datetime
import logging
import urllib.request
from enum import Enum  #
from typing import Optional, Union

from flask import Request
from telegram import (
    Bot,
    Update,
)

from _dependencies.commons import (
    Topics,
    get_app_config,
    publish_to_pubsub,
    setup_google_logging,
    sql_connect_by_psycopg2,
)
from _dependencies.misc import (
    notify_admin,
)
from communicate._utils.buttons import (
    b_act_titles,
    b_admin_menu,
    b_coords_check,
    b_coords_del,
    b_coords_man_def,
    b_help_no,
    b_help_yes,
    b_menu_set_region,
    b_no_its_not_me,
    b_orders_done,
    b_orders_tbd,
    b_reg_moscow,
    b_reg_not_moscow,
    b_test_menu,
    b_test_search_follow_mode_off,
    b_yes_its_me,
    reply_markup_main,
)
from communicate._utils.handlers import (
    handle_admin_menu,
    handle_age_preferences,
    handle_coordinates_1,
    handle_coordinates_check,
    handle_coordinates_deletion,
    handle_federal_district,
    handle_finish_onboarding,
    handle_first_search,
    handle_full_dict_of_regions,
    handle_goto_community,
    handle_help_message,
    handle_leave_testing,
    handle_map_open,
    handle_no_help,
    handle_notification_preferences,
    handle_off_search_mode,
    handle_other_menu,
    handle_photos,
    handle_role_select,
    handle_search_mode_on_off,
    handle_set_pref_coordinates,
    handle_set_region,
    handle_set_region_2,
    handle_set_urgency_1,
    handle_settings_menu,
    handle_start,
    handle_start_testing,
    handle_surgency_settings,
    handle_view_searches,
)
from communicate._utils.services import (
    get_coordinates_from_string,
    inline_processing,
    process_unneeded_messages,
    process_user_coordinates,
    run_onboarding,
)

from ._utils.buttons import (
    AgePreferencesMenu,
    AllButtons,
    Commands,
    DistanceSettings,
    MainMenu,
    MainSettingsMenu,
    NotificationSettingsMenu,
    OtherMenu,
    RoleChoice,
    UrgencySettings,
    b_back_to_start,
    b_fed_dist_pick_other,
    c_start,
    dict_of_fed_dist,
    full_buttons_dict,
    full_dict_of_regions,
    keyboard_fed_dist_set,
)
from ._utils.database import (
    check_if_new_user,
    check_onboarding_step,
    delete_last_user_inline_dialogue,
    get_last_bot_msg,
    get_last_user_inline_dialogue,
    get_user_reg_folders_preferences,
    get_user_role,
    save_bot_reply_to_user,
    save_new_user,
    save_user_message_to_bot,
)
from ._utils.services import (
    make_api_call,
    manage_if_moscow,
    manage_linking_to_forum,
    manage_radius,
    manage_search_whiteness,
    manage_topic_type,
    process_block_unblock_user,
    process_response_of_api_call,
)

setup_google_logging()

# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but jest informational warnings that there were retries, that's why we exclude them
logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


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


def main(request: Request) -> str:
    """Main function to orchestrate the whole script"""

    if request.method != 'POST':
        logging.error(f'non-post request identified {request}')
        return 'it was not post request'

    bot_token = get_app_config().bot_api_token__prod
    bot = Bot(token=bot_token)
    update = get_the_update(bot, request)

    try:
        with sql_connect_by_psycopg2() as conn_psy, conn_psy.cursor() as cur:
            return process_update(cur, update)
    except Exception as e:
        logging.info('GENERAL COMM CRASH:')
        logging.exception(e)
        notify_admin('[comm] general script fail')


def process_update(cur, update: Update) -> str:
    keyboard_other = [
        [OtherMenu.b_view_latest_searches],
        [OtherMenu.b_goto_first_search],
        [OtherMenu.b_goto_community],
        [OtherMenu.b_goto_photos],
        [b_back_to_start],
    ]
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

    # basic markup which will be substituted for all specific cases
    reply_markup = reply_markup_main
    # placeholder for the New message from bot as reply to "update". Placed here – to avoid errors of GCF
    bot_message = ''

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

        return 'finished successfully. in was a message with user coordinates'

    # all other cases when bot was not able to understand the message from user
    if not got_message:
        logging.info('DBG.C.6. THERE IS a COMM SCRIPT INVOCATION w/O MESSAGE:')
        logging.info(str(update))
        text_for_admin = (
            f'[comm]: Empty message in Comm, user={user_id}, username={username}, '
            f'got_message={got_message}, update={update}, '
            f'bot_request_bfr_usr_msg={bot_request_bfr_usr_msg}'
        )
        logging.info(text_for_admin)
        notify_admin(text_for_admin)

        return 'finished successfully. No incoming message'

    # if there is a text message from user
    # if pushed \start
    if got_message == c_start:
        bot_message, reply_markup = handle_start(bot_token, user_id, user_is_new)

    elif (
        onboarding_step_id == 20 and got_message in full_dict_of_regions
    ) or got_message == b_reg_moscow:  # "moscow_replied"
        # FIXME – 02.12.2023 – un-hiding menu button for the newcomers
        #  (in the future it should be done in manage_user script)
        bot_message, reply_markup = handle_finish_onboarding(cur, bot_token, got_message, username, user_id, user_role)

    elif got_message in {
        RoleChoice.b_role_looking_for_person,
        RoleChoice.b_role_want_to_be_la,
        RoleChoice.b_role_iam_la,
        RoleChoice.b_role_secret,
        RoleChoice.b_role_other,
        b_orders_done,
        b_orders_tbd,
    }:
        # save user role & onboarding stage
        bot_message, reply_markup, user_role = handle_role_select(cur, got_message, username, user_id)

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
        bot_message, reply_markup = handle_no_help()

    elif got_message == b_help_yes:
        bot_message, reply_markup = handle_help_message()

    # set user pref: urgency
    elif got_message in UrgencySettings.list():
        bot_message, reply_markup = handle_surgency_settings(cur, got_message, user_id)

    # force user to input a region
    elif not user_regions and not (
        got_message in full_dict_of_regions
        or got_message in dict_of_fed_dist
        or got_message in {b_menu_set_region, c_start, MainMenu.b_settings, Commands.c_settings}
    ):
        bot_message, reply_markup = handle_set_region_2(user_id)

    elif got_callback and got_callback['action'] == 'search_follow_mode':  # issue#425
        bot_message, reply_markup = manage_search_whiteness(
            cur, user_id, got_callback, callback_query_id, callback_query, bot_token
        )

    elif got_callback and got_callback['action'] in [
        'search_follow_mode_on',
        'search_follow_mode_off',
    ]:  # issue#425
        bot_message, reply_markup = handle_search_mode_on_off(
            cur, bot_token, user_id, got_callback, callback_query_id, callback_query
        )

    # Send summaries
    elif got_message in {
        OtherMenu.b_view_latest_searches,
        MainMenu.b_view_act_searches,
        Commands.c_view_latest_searches,
        Commands.c_view_act_searches,
    }:
        bot_message, reply_markup, msg_sent_by_specific_code = handle_view_searches(
            cur, bot_token, got_message, user_id, user_regions, bot_message, reply_markup
        )

    # Perform individual replies

    # Admin mode
    elif got_message.lower() == b_admin_menu:
        bot_message, reply_markup = handle_admin_menu()

    # FIXME - WIP
    elif got_message.lower() == b_test_menu:
        bot_message, reply_markup = handle_start_testing(cur, user_id)
    # FIXME ^^^

    elif got_message.lower() == 'notest':
        bot_message, reply_markup = handle_leave_testing(cur, user_id)

    ###            elif got_message.lower() == b_test_search_follow_mode_on: #issue425
    ###                set_search_follow_mode(cur, user_id, True)
    ###                bot_message = 'Возможность отслеживания поисков включена. Возвращаемся в главное меню.'
    ###                reply_markup = reply_markup_main

    elif got_message.lower() == b_test_search_follow_mode_off:  ##remains for some time for emrgency case
        bot_message, reply_markup = handle_off_search_mode(cur, user_id)

    elif got_message in {MainMenu.b_map, Commands.c_map}:
        bot_message, reply_markup = handle_map_open()

    elif (
        got_message == b.set.topic_type.text
        or b.topic_types.contains(got_message)
        or (got_hash and b.topic_types.contains(got_hash))
    ):  # noqa
        callback_query_message_id = callback_query.message.id if callback_query else None
        bot_message, reply_markup = manage_topic_type(
            cur, user_id, got_message, b, got_callback, callback_query_id, bot_token, callback_query_message_id
        )

    elif got_message in {MainSettingsMenu.b_set_pref_age} or got_message in AgePreferencesMenu.list():
        bot_message, reply_markup = handle_age_preferences(cur, got_message, user_id)

    elif (
        got_message == MainSettingsMenu.b_set_pref_radius
        or got_message in DistanceSettings.list()
        or bot_request_bfr_usr_msg == 'radius_input'
    ):
        bot_message, reply_markup, bot_request_aft_usr_msg = manage_radius(
            cur,
            user_id,
            got_message,
            MainSettingsMenu.b_set_pref_radius,
            DistanceSettings.b_pref_radius_act,
            DistanceSettings.b_pref_radius_deact,
            DistanceSettings.b_pref_radius_change,
            b_back_to_start,
            MainSettingsMenu.b_set_pref_coords,
            bot_request_bfr_usr_msg,
        )

    elif (
        got_message in {MainSettingsMenu.b_set_forum_nick, b_yes_its_me, b_no_its_not_me}
        or bot_request_bfr_usr_msg == 'input_of_forum_username'
    ):
        bot_message, reply_markup, bot_request_aft_usr_msg = manage_linking_to_forum(
            cur,
            got_message,
            user_id,
            MainSettingsMenu.b_set_forum_nick,
            b_back_to_start,
            bot_request_bfr_usr_msg,
            b_admin_menu,
            b_test_menu,
            b_yes_its_me,
            b_no_its_not_me,
            MainMenu.b_settings,
            reply_markup_main,
        )

    elif got_message == MainSettingsMenu.b_set_pref_urgency:
        bot_message, reply_markup = handle_set_urgency_1()

    # DEBUG: for debugging purposes only
    elif got_message.lower() == 'go':
        publish_to_pubsub(Topics.topic_notify_admin, 'test_admin_check')

    elif got_message in {MainMenu.b_other, Commands.c_other}:
        bot_message, reply_markup = handle_other_menu(keyboard_other)

    elif got_message in {b_menu_set_region, b_fed_dist_pick_other}:
        bot_message, reply_markup = handle_set_region(cur, got_message, user_id)

    elif got_message in dict_of_fed_dist:
        bot_message, reply_markup = handle_federal_district(cur, got_message, user_id)

    elif got_message in full_dict_of_regions:
        bot_message, reply_markup = handle_full_dict_of_regions(
            cur, got_message, username, user_id, onboarding_step_id, user_role
        )

    elif got_message in {MainMenu.b_settings, Commands.c_settings}:
        bot_message, reply_markup = handle_settings_menu(cur, user_id)

    elif got_message == MainSettingsMenu.b_set_pref_coords:
        bot_message, reply_markup = handle_set_pref_coordinates()

    elif got_message == b_coords_del:
        bot_message, reply_markup = handle_coordinates_deletion(cur, user_id)

    elif got_message == b_coords_man_def:
        bot_message, reply_markup, bot_request_aft_usr_msg = handle_coordinates_1()

    elif got_message == b_coords_check:
        bot_message, reply_markup = handle_coordinates_check(cur, user_id)

    elif got_message == b_back_to_start:
        bot_message = 'возвращаемся в главное меню'
        reply_markup = reply_markup_main

    elif got_message == OtherMenu.b_goto_community:
        bot_message, reply_markup = handle_goto_community()

    elif got_message == OtherMenu.b_goto_first_search:
        bot_message, reply_markup = handle_first_search()

    elif got_message == OtherMenu.b_goto_photos:
        bot_message, reply_markup = handle_photos()

    # special block for flexible menu on notification preferences
    elif (
        got_message in {MainSettingsMenu.b_set_pref_notif_type, b_act_titles}
        or got_message in NotificationSettingsMenu.list()
    ):
        # save preference for +ALL
        bot_message, reply_markup = handle_notification_preferences(cur, got_message, user_id)

    # in case of other user messages:
    else:
        # If command in unknown
        bot_message = 'не понимаю такой команды, пожалуйста, используйте кнопки со стандартными ' 'командами ниже'
        reply_markup = reply_markup_main

    finalize_bot_response(
        cur,
        bot_token,
        user_id,
        got_hash,
        got_callback,
        callback_query,
        reply_markup,
        bot_request_aft_usr_msg,
        msg_sent_by_specific_code,
        bot_message,
    )

    return 'finished successfully. in was a regular conversational message'


def finalize_bot_response(
    cur,
    bot_token,
    user_id,
    got_hash,
    got_callback,
    callback_query,
    reply_markup,
    bot_request_aft_usr_msg,
    msg_sent_by_specific_code,
    bot_message,
):
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

    if bot_message:
        save_bot_reply_to_user(cur, user_id, bot_message)
