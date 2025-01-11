"""Script send the Debug messages to Admin via special Debug Bot in telegram https://t.me/la_test_1_bot
To receive notifications one should be marked as Admin in PSQL"""

import asyncio
import base64
import datetime
import logging
import urllib.request

import google.cloud.logging
from google.cloud import secretmanager
from telegram.ext import Application, ContextTypes

url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
req = urllib.request.Request(url)
req.add_header('Metadata-Flavor', 'Google')
project_id = urllib.request.urlopen(req).read().decode()

client = secretmanager.SecretManagerServiceClient()

log_client = google.cloud.logging.Client()
log_client.setup_logging()

logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


def get_secrets(secret_request):
    """get google cloud secret"""

    name = f'projects/{project_id}/secrets/{secret_request}/versions/latest'
    response = client.access_secret_version(name=name)

    return response.payload.data.decode('UTF-8')


def process_pubsub_message(event):
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


async def prepare_message_for_async(user_id, data):
    bot_token = get_secrets('bot_api_token')
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

    admin_user_id = get_secrets('my_telegram_id')

    send_message(admin_user_id, message_from_pubsub)

    return None
