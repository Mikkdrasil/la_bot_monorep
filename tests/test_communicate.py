from unittest.mock import MagicMock, Mock

import pytest
from psycopg2.extensions import cursor

import communicate._utils.buttons
import communicate._utils.database
import communicate._utils.services
from _dependencies.commons import get_app_config, sql_connect_by_psycopg2
from communicate import main
from tests.factories.telegram import get_callback_query, get_reply_markup


@pytest.fixture
def cur() -> cursor:
    with sql_connect_by_psycopg2() as conn, conn.cursor() as cur:
        yield cur


def test_update_and_download_list_of_regions():
    main.main(MagicMock())


def test_manage_search_follow_mode(cur):
    # NO SMOKE TEST communicate.main.manage_search_follow_mode
    user_action = 'search_follow_mode_on'
    bot_answer = main.manage_search_follow_mode(cur, '1', {'action': user_action}, 2, 3, 'token')
    assert bot_answer == 'Режим выбора поисков для отслеживания включен.'

    user_action = 'search_follow_mode_off'
    bot_answer = main.manage_search_follow_mode(cur, '1', {'action': user_action}, 2, 3, 'token')
    assert bot_answer == 'Режим выбора поисков для отслеживания отключен.'


def test_manage_search_whiteness(cur):
    # NO SMOKE TEST communicate.main.manage_search_whiteness
    cb_query = get_callback_query()
    user_callback = {'action': 'search_follow_mode', 'hash': '123', 'text': '   '}
    res = communicate._utils.services.manage_search_whiteness(cur, 1, user_callback, 1, cb_query, 'token')

    assert res[0] == 'foo'


def test_manage_topic_type(cur):
    # NO SMOKE TEST communicate.main.manage_topic_type
    cb_query = get_callback_query()
    user_callback = {'action': 'on', 'hash': '7bf077a5', 'text': '   '}
    res = communicate._utils.services.manage_topic_type(
        cur,
        1,
        'foo',
        communicate._utils.buttons.AllButtons(communicate._utils.buttons.full_buttons_dict),
        user_callback,
        1,
        'token',
        cb_query,
    )

    assert (
        res[0]
        == 'Вы можете выбрать и в любой момент поменять, по каким типам поисков или мероприятий бот должен присылать уведомления.'
    )


def test_api_callback_edit_inline_keyboard(cur):
    # NO SMOKE TEST communicate.main.api_callback_edit_inline_keyboard
    cb_query = get_callback_query().to_dict()
    res = main.api_callback_edit_inline_keyboard(get_app_config().bot_api_token__prod, cb_query, get_reply_markup(), 1)

    assert res == 'failed'


def test_manage_age(cur):
    # NO SMOKE TEST communicate.main.manage_age
    res = communicate._utils.services.manage_age(cur, 1, 'включить: Маленькие Дети 0-6 лет')

    assert res[0][0] == ['отключить: Маленькие Дети 0-6 лет']


def test_save_onboarding_step():
    # NO SMOKE TEST communicate.main.save_onboarding_step
    res = communicate._utils.services.save_onboarding_step(1, 'testuser', 'step')

    assert res is None


def test_send_message_to_api():
    # NO SMOKE TEST communicate.main.send_message_to_api
    message = 'foo'
    params = {'parse_mode': 'markdown'}
    res = main.send_message_to_api('token', 1, message, params)

    assert res == 'failed'


def test_send_callback_answer_to_api():
    # NO SMOKE TEST communicate.main.send_callback_answer_to_api
    message = 'foo'
    res = communicate._utils.services.send_callback_answer_to_api('token', 1, message)

    assert res == 'failed'
