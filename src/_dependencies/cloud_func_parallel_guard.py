import datetime
import json
import logging

from _dependencies.commons import sql_connect_by_psycopg2

# from compose_notifications.main import LineInChangeLog


def check_if_other_functions_are_working(func_name: str, interval_seconds: int) -> bool:
    """Check in PSQL in there's the same function 'send_notifications' working in parallel"""

    with sql_connect_by_psycopg2() as conn_psy, conn_psy.cursor() as cur:
        sql_text_psy = f"""
                        SELECT 
                            event_id 
                        FROM
                            functions_registry
                        WHERE
                            time_start > NOW() - interval '{interval_seconds} seconds' AND
                            time_finish IS NULL AND
                            cloud_function_name  = '{func_name}'
                        ;
                        /*action='check_if_there_is_parallel_notif_function' */
                        ;"""

        cur.execute(sql_text_psy)
        lines = cur.fetchone()

        parallel_functions_are_running = bool(lines)

    return parallel_functions_are_running


def record_start_of_function(event_num: int, function_num: int, triggered_by_func_num: int, function_name: str) -> None:
    """Record into PSQL that this function started working (id = id of the respective pub/sub event)"""

    with sql_connect_by_psycopg2() as conn_psy, conn_psy.cursor() as cur:
        sql_text_psy = """
                        INSERT INTO 
                            functions_registry
                        (event_id, time_start, cloud_function_name, function_id, triggered_by_func_id)
                        VALUES
                        (%s, %s, %s, %s, %s);
                        /*action='save_start_of_notif_function' */
                        ;"""

        cur.execute(
            sql_text_psy,
            (event_num, datetime.datetime.now(), function_name, function_num, triggered_by_func_num),
        )
        logging.info(f'function was triggered by event {event_num}, we assigned a function_id = {function_num}')


def record_finish_of_function(event_num: int, list_of_changed_ids: list) -> None:
    """Record into PSQL that this function finished working (id = id of the respective pub/sub event)"""
    with sql_connect_by_psycopg2() as conn_psy, conn_psy.cursor() as cur:
        json_of_params = json.dumps({'ch_id': list_of_changed_ids})

        sql_text_psy = """
                        UPDATE 
                            functions_registry
                        SET
                            time_finish = %s,
                            params = %s
                        WHERE
                            event_id = %s
                        ;
                        /*action='save_finish_of_notif_function' */
                        ;"""

        cur.execute(sql_text_psy, (datetime.datetime.now(), json_of_params, event_num))


def check_and_save_event_id(
    context,
    event: str,
    function_id: int,
    list_of_change_log_ids: list[int] | None,
    triggered_by_func_id: int,
    func_name: str,
    interval: int,
) -> bool:
    """Work with PSQL table functions_registry. Goal of the table & function is to avoid parallel work of
    two compose_notifications functions. Executed in the beginning and in the end of compose_notifications function"""
    # TODO try decompose
    if not context or not event:
        return False

    try:
        event_id = context.event_id
    except Exception as e:  # noqa
        return False

    # if this functions is triggered in the very beginning of the Google Cloud Function execution
    if event == 'start':
        if check_if_other_functions_are_working(func_name, interval):
            record_start_of_function(event_id, function_id, triggered_by_func_id, func_name)
            return True

        record_start_of_function(event_id, function_id, triggered_by_func_id, func_name)
        return False

    # if this functions is triggered in the very end of the Google Cloud Function execution
    elif event == 'finish':
        record_finish_of_function(event_id, list_of_change_log_ids or [])
        return False
