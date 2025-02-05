"""compose and save all the text / location messages, then initiate sending via pub-sub"""

import datetime
import logging
from typing import Any

import sqlalchemy
from sqlalchemy.engine.base import Connection

from _dependencies.cloud_func_parallel_guard import check_and_save_event_id
from _dependencies.commons import Topics, publish_to_pubsub, setup_google_logging, sqlalchemy_get_pool
from _dependencies.misc import (
    generate_random_function_id,
    get_triggering_function,
    process_pubsub_message_v2,
)

from ._utils.log_record_composer import LogRecordExtractor
from ._utils.notif_common import LineInChangeLog, User
from ._utils.notifications_maker import NotificationComposer
from ._utils.users_list_composer import UsersListComposer

INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS = 130
FUNC_NAME = 'compose_notifications'


setup_google_logging()


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 60)


def get_list_of_admins_and_testers(conn: Connection) -> tuple[list[int], list[int]]:
    """
    get the list of users with admin & testers roles from PSQL
    for debug only
    """

    list_of_admins = []
    list_of_testers = []

    try:
        user_roles = conn.execute("""SELECT user_id, role FROM user_roles;""").fetchall()

        for line in user_roles:
            if line[1] == 'admin':
                list_of_admins.append(line[0])
            elif line[1] == 'tester':
                list_of_testers.append(line[0])

        logging.info('Got the Lists of Admins & Testers')

    except Exception as e:
        logging.info('Not able to get the lists of Admins & Testers ')
        logging.exception(e)

    return list_of_admins, list_of_testers

    # TODO ^^^


def call_self_if_need_compose_more(conn: Connection, function_id: int) -> None:
    """check if there are any notifications remained to be composed"""

    check = conn.execute("""SELECT search_forum_num, changed_field, new_value, id, change_type FROM change_log
                            WHERE notification_sent is NULL
                            OR notification_sent='s' LIMIT 1; """).fetchall()
    if check:
        logging.info('we checked – there is still something to compose: re-initiating [compose_notification]')
        message_for_pubsub = {'triggered_by_func_id': function_id, 'text': 're-run from same script'}
        # TODO remove recursion if possible
        publish_to_pubsub(Topics.topic_for_notification, message_for_pubsub)
    else:
        logging.info('we checked – there is nothing to compose: we are not re-initiating [compose_notification]')


def create_user_notifications_from_change_log_record(
    analytics_start_of_func: datetime.datetime,
    function_id: int,
    conn: Connection,
    new_record: LineInChangeLog,
    list_of_users: list[User],
) -> datetime.datetime:
    # compose Users List: all the notifications recipients' details

    analytics_match_finish = datetime.datetime.now()
    duration_match = round((analytics_match_finish - analytics_start_of_func).total_seconds(), 2)
    logging.info(f'time: function match end-to-end – {duration_match} sec')

    # check the matrix: new update - user and initiate sending notifications

    composer = NotificationComposer(conn)
    composer.generate_notifications_for_users(new_record, list_of_users, function_id)

    analytics_iterations_finish = datetime.datetime.now()
    duration_iterations = round((analytics_iterations_finish - analytics_match_finish).total_seconds(), 2)
    logging.info(f'time: function iterations end-to-end – {duration_iterations} sec')

    # mark all the "new" lines in tables Change Log & Comments as "old"
    composer.mark_new_record_as_processed(new_record)
    composer.mark_new_comments_as_processed(new_record)

    # final step – update statistics on how many users received notifications on new searches
    composer.record_notification_statistics()
    return analytics_iterations_finish  # TODO can we move it out of this function?


def main(event: dict, context: str) -> Any:  # noqa
    """key function which is initiated by Pub/Sub"""

    analytics_start_of_func = datetime.datetime.now()

    function_id = generate_random_function_id()
    message_from_pubsub = process_pubsub_message_v2(event)
    triggered_by_func_id = get_triggering_function(message_from_pubsub)  # type:ignore[arg-type]

    there_is_function_working_in_parallel = check_and_save_event_id(
        context,
        'start',
        function_id,
        None,
        triggered_by_func_id,
        FUNC_NAME,
        INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS,
    )
    if there_is_function_working_in_parallel:
        logging.info('function execution stopped due to parallel run with another function')
        check_and_save_event_id(
            context,
            'finish',
            function_id,
            None,
            triggered_by_func_id,
            FUNC_NAME,
            INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS,
        )
        logging.info('script finished')
        return

    list_of_change_log_ids = []
    pool = sql_connect()
    with pool.connect() as conn:
        # compose New Records List: the delta from Change log
        new_record = LogRecordExtractor(conn).get_line()
        # TODO change to class

        # only if there are updates in Change Log
        if new_record:
            list_of_users = UsersListComposer(conn).get_users_list_for_line_in_change_log(new_record)

            analytics_iterations_finish = create_user_notifications_from_change_log_record(
                analytics_start_of_func,
                function_id,
                conn,
                new_record,
                list_of_users,
            )

            try:
                list_of_change_log_ids = [new_record.change_id]
            except Exception as e:  # noqa
                logging.exception(e)

        call_self_if_need_compose_more(conn, function_id)

    check_and_save_event_id(
        context,
        'finish',
        function_id,
        list_of_change_log_ids,
        triggered_by_func_id,
        FUNC_NAME,
        INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS,
    )

    analytics_finish = datetime.datetime.now()
    if new_record:
        duration_saving = round((analytics_finish - analytics_iterations_finish).total_seconds(), 2)
        logging.info(f'time: function data saving – {duration_saving} sec')

    duration_full = round((analytics_finish - analytics_start_of_func).total_seconds(), 2)
    logging.info(f'time: function full end-to-end – {duration_full} sec')

    logging.info('script finished')
