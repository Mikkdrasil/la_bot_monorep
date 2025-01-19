"""Script send the Debug messages to Admin via special Debug Bot in telegram https://t.me/la_test_1_bot
To receive notifications one should be marked as Admin in PSQL"""

import asyncio
import base64
import datetime
import logging
from typing import Any, Dict, Optional

from telegram.ext import Application, ContextTypes

from _dependencies.commons import get_app_config, setup_google_logging

from ._utils.foo import test_func

test_func()
setup_google_logging()

logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


def process_pubsub_message(event: dict):
    """get the text message from pubsub"""

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
        encoded_to_ascii = eval(received_message_from_pubsub)
        data_in_ascii = encoded_to_ascii['data']
        message_in_ascii = data_in_ascii['message']
    else:
        message_in_ascii = 'ERROR: I cannot read message from pub/sub'

    return message_in_ascii


async def send_message_async(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=context.job.chat_id, **context.job.data)

    return None


async def prepare_message_for_async(user_id, data: Dict[str, str]) -> str:
    bot_token = get_app_config().bot_api_token
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
    # TODO DOUBLE
    asyncio.run(prepare_message_for_async(user_id, data))


def send_message(admin_user_id, message):
    """send individual notification message to telegram (debug)"""

    try:
        # to avoid 4000 symbols restriction for telegram message
        if len(message) > 3500:
            message = message[:1500]

        data = {'text': message}
        process_sending_message_async(user_id=admin_user_id, data=data)

    except Exception as e:
        logging.info('[send_debug]: send debug to telegram failed')
        logging.exception(e)

        try:
            debug_message = f'ERROR! {datetime.datetime.now()}: {e}'

            data = {'text': debug_message}
            process_sending_message_async(user_id=admin_user_id, data=data)

        except Exception as e2:
            logging.exception(e2)

    return None


def main(event, context):  # noqa
    """main function, envoked by pub/sub, which sends the notification to Admin"""  # noqa

    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    logging.info('[send_debug]: received from pubsub: {}'.format(pubsub_message))  # noqa

    message_from_pubsub = process_pubsub_message(event)

    admin_user_id = get_app_config().my_telegram_id

    send_message(admin_user_id, message_from_pubsub)

    return None
