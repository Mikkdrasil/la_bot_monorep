"""compose and save all the text / location messages, then initiate sending via pub-sub"""

import datetime
import logging
import re
from typing import Any, List, Optional, Tuple

import sqlalchemy
from sqlalchemy.engine.base import Connection

from _dependencies.cloud_func_parallel_guard import check_and_save_event_id
from _dependencies.commons import Topics, get_app_config, publish_to_pubsub, setup_google_logging, sqlalchemy_get_pool
from _dependencies.misc import (
    generate_random_function_id,
    get_triggering_function,
    notify_admin,
    process_pubsub_message_v2,
)

from ._utils.enrich import (
    define_dist_and_dir_to_search,
    enrich_new_record_from_searches,
    enrich_new_record_with_clickable_name,
    enrich_new_record_with_com_message_texts,
    enrich_new_record_with_comments,
    enrich_new_record_with_emoji,
    enrich_new_record_with_managers,
    enrich_new_record_with_search_activities,
    enrich_users_list_with_age_periods,
    enrich_users_list_with_radius,
)
from ._utils.notif_common import COORD_FORMAT, LineInChangeLog, User

setup_google_logging()


INTERVAL_TO_CHECK_PARALLEL_FUNCTION_SECONDS = 130
FUNC_NAME = 'compose_notifications'

stat_list_of_recipients = []  # list of users who received notification on new search
fib_list = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]
CLEANER_RE = re.compile('<.*?>')


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 60)


def compose_new_records_from_change_log(conn: Connection) -> LineInChangeLog:
    """compose the New Records list of the unique New Records in Change Log: one Record = One line in Change Log"""

    delta_in_cl = conn.execute(
        """SELECT search_forum_num, changed_field, new_value, id, change_type FROM change_log
        WHERE notification_sent is NULL
        OR notification_sent='s' ORDER BY id LIMIT 1; """
    ).fetchall()

    if not delta_in_cl:
        logging.info('no new records found in PSQL')
        return None

    if not len(list(delta_in_cl)) > 0:
        logging.info(f'new record is found in PSQL, however it is not list: {delta_in_cl}')
        return None

    one_line_in_change_log = [i for i in delta_in_cl[0]]

    if not one_line_in_change_log:
        logging.info(f'new record is found in PSQL, however it is not list: {delta_in_cl}, {one_line_in_change_log}')
        return None

    logging.info(f'new record is {one_line_in_change_log}')
    new_record = LineInChangeLog()
    new_record.forum_search_num = one_line_in_change_log[0]
    new_record.changed_field = one_line_in_change_log[1]
    new_record.new_value = one_line_in_change_log[2]
    new_record.change_id = one_line_in_change_log[3]
    new_record.change_type = one_line_in_change_log[4]

    # TODO – there was a filtering for duplication: Inforg comments vs All Comments, but after restructuring
    #  of the scrip tech solution stopped working. The new filtering solution to be developed

    logging.info(f'New Record composed from Change Log: {str(new_record)}')

    return new_record


def compose_users_list_from_users(conn: Connection, new_record: LineInChangeLog) -> List:
    """compose the Users list from the tables Users & User Coordinates: one Record = one user"""

    list_of_users = []

    try:
        analytics_prefix = 'users list'
        analytics_start = datetime.datetime.now()

        sql_text_psy = sqlalchemy.text("""
                WITH
                    user_list AS (
                        SELECT user_id, username_telegram, role
                        FROM users WHERE status IS NULL or status='unblocked'),
                    user_notif_pref_prep AS (
                        SELECT user_id, array_agg(pref_id) aS agg
                        FROM user_preferences GROUP BY user_id),
                    user_notif_type_pref AS (
                        SELECT user_id, CASE WHEN 30 = ANY(agg) THEN True ELSE False END AS all_notifs
                        FROM user_notif_pref_prep
                        WHERE (30 = ANY(agg) OR :a = ANY(agg))
                            AND NOT (4/*topic_inforg_comment_new*/ = ANY(agg)
                                AND :a = 2/*topic_title_change*/)),/*AK20240409:issue13*/
                    user_folders_prep AS (
                        SELECT user_id, forum_folder_num,
                            CASE WHEN count(forum_folder_num) OVER (PARTITION BY user_id) > 1
                                THEN TRUE ELSE FALSE END as multi_folder
                        FROM user_regional_preferences),
                    user_folders AS (
                        SELECT user_id, forum_folder_num, multi_folder
                        FROM user_folders_prep WHERE forum_folder_num= :b),
                    user_topic_pref_prep AS (
                        SELECT user_id, array_agg(topic_type_id) aS agg
                        FROM user_pref_topic_type GROUP BY user_id),
                    user_topic_type_pref AS (
                        SELECT user_id, agg AS all_types
                        FROM user_topic_pref_prep
                        WHERE 30 = ANY(agg) OR :c = ANY(agg)),
                    user_short_list AS (
                        SELECT ul.user_id, ul.username_telegram, ul.role , uf.multi_folder, up.all_notifs
                        FROM user_list as ul
                        LEFT JOIN user_notif_type_pref AS up
                        ON ul.user_id=up.user_id
                        LEFT JOIN user_folders AS uf
                        ON ul.user_id=uf.user_id
                        LEFT JOIN user_topic_type_pref AS ut
                        ON ul.user_id=ut.user_id
                        WHERE
                            uf.forum_folder_num IS NOT NULL AND
                            up.all_notifs IS NOT NULL AND
                            ut.all_types IS NOT NULL),
                    user_with_loc AS (
                        SELECT u.user_id, u.username_telegram, uc.latitude, uc.longitude,
                            u.role, u.multi_folder, u.all_notifs
                        FROM user_short_list AS u
                        LEFT JOIN user_coordinates as uc
                        ON u.user_id=uc.user_id)

                SELECT ns.user_id, ns.username_telegram, ns.latitude, ns.longitude, ns.role,
                    st.num_of_new_search_notifs, ns.multi_folder, ns.all_notifs
                FROM user_with_loc AS ns
                LEFT JOIN user_stat st
                ON ns.user_id=st.user_id
                /*action='get_user_list_filtered_by_folder_and_notif_type' */;""")

        users_short_version = conn.execute(
            sql_text_psy, a=new_record.change_type, b=new_record.forum_folder, c=new_record.topic_type_id
        ).fetchall()

        analytics_sql_finish = datetime.datetime.now()
        duration_sql = round((analytics_sql_finish - analytics_start).total_seconds(), 2)
        logging.info(f'time: {analytics_prefix} sql – {duration_sql} sec')

        if users_short_version:
            logging.info(f'{users_short_version}')
            users_short_version = list(users_short_version)

        for line in users_short_version:
            new_line = User(
                user_id=line[0],
                username_telegram=line[1],
                user_latitude=line[2],
                user_longitude=line[3],
                user_role=line[4],
                user_in_multi_folders=line[6],
                all_notifs=line[7],
            )
            if line[5] == 'None' or line[5] is None:
                new_line.user_new_search_notifs = 0
            else:
                new_line.user_new_search_notifs = int(line[5])

            list_of_users.append(new_line)

        analytics_match_finish = datetime.datetime.now()
        duration_match = round((analytics_match_finish - analytics_sql_finish).total_seconds(), 2)
        logging.info(f'time: {analytics_prefix} match – {duration_match} sec')
        duration_full = round((analytics_match_finish - analytics_start).total_seconds(), 2)
        logging.info(f'time: {analytics_prefix} end-to-end – {duration_full} sec')

        logging.info('User List composed')

    except Exception as e:
        logging.error('Not able to compose Users List: ' + repr(e))
        logging.exception(e)

    return list_of_users


def get_list_of_admins_and_testers(conn):
    """get the list of users with admin & testers roles from PSQL"""

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


def save_to_sql_notif_by_user(
    conn: sqlalchemy.engine.Connection,
    mailing_id_,
    user_id_,
    message_,
    message_without_html_,
    message_type_,
    message_params_,
    message_group_id_,
    change_log_id_,
):
    """save to sql table notif_by_user the new message"""

    # record into SQL table notif_by_user
    sql_text_ = sqlalchemy.text("""
                        INSERT INTO notif_by_user (
                            mailing_id,
                            user_id,
                            message_content,
                            message_text,
                            message_type,
                            message_params,
                            message_group_id,
                            change_log_id,
                            created)
                        VALUES (:a, :b, :c, :d, :e, :f, :g, :h, :i);
                        """)

    conn.execute(
        sql_text_,
        a=mailing_id_,
        b=user_id_,
        c=message_,
        d=message_without_html_,
        e=message_type_,
        f=message_params_,
        g=message_group_id_,
        h=change_log_id_,
        i=datetime.datetime.now(),
    )

    return None


def get_from_sql_if_was_notified_already(conn: sqlalchemy.engine.Connection, user_id_, message_type_, change_log_id_):
    """check in sql if this user was already notified re this change_log record
    works for every user during iterations over users"""

    sql_text_ = sqlalchemy.text("""
        SELECT EXISTS (
            SELECT
                message_id
            FROM
                notif_by_user
            WHERE
                completed IS NOT NULL AND
                user_id=:b AND
                message_type=:c AND
                change_log_id=:a
        )
        /*action='get_from_sql_if_was_notified_already_new'*/
        ;
    """)

    user_was_already_notified = conn.execute(sql_text_, a=change_log_id_, b=user_id_, c=message_type_).fetchone()[0]

    return user_was_already_notified


def get_from_sql_list_of_users_with_prepared_message(conn: sqlalchemy.engine.Connection, change_log_id_):
    """check what is the list of users for whom we already composed messages for the given change_log record"""

    sql_text_ = sqlalchemy.text("""
        SELECT
            user_id
        FROM
            notif_by_user
        WHERE
            created IS NOT NULL AND
            change_log_id=:a

        /*action='get_from_sql_list_of_users_with_already_composed_messages 2.0'*/
        ;
        """)

    raw_data_ = conn.execute(sql_text_, a=change_log_id_).fetchall()
    # TODO: to delete
    logging.info('list of user with composed messages:')
    logging.info(raw_data_)

    users_who_were_composed = []
    for line in raw_data_:
        users_who_were_composed.append(line[0])

    return users_who_were_composed


def get_the_new_group_id(conn):
    """define the max message_group_id in notif_by_user and add +1"""

    raw_data_ = conn.execute("""SELECT MAX(message_group_id) FROM notif_by_user
    /*action='get_the_new_group_id'*/
    ;""").fetchone()

    if raw_data_[0]:
        next_id = raw_data_[0] + 1
    else:
        next_id = 0

    return next_id


def process_mailing_id(conn: sqlalchemy.engine.Connection, change_log_item, topic_id, change_type):
    """TODO"""

    # check if this change_log record was somehow processed
    sql_text = sqlalchemy.text("""SELECT EXISTS (SELECT * FROM notif_mailings WHERE change_log_id=:a);""")
    record_was_processed_already = conn.execute(sql_text, a=change_log_item).fetchone()[0]

    # TODO: DEBUG
    if record_was_processed_already:
        logging.info('[comp_notif]: 2 MAILINGS for 1 CHANGE LOG RECORD identified')
    # TODO: DEBUG

    # record into SQL table notif_mailings
    sql_text = sqlalchemy.text("""
                    INSERT INTO notif_mailings (topic_id, source_script, mailing_type, change_log_id)
                    VALUES (:a, :b, :c, :d)
                    RETURNING mailing_id;
                    """)
    raw_data = conn.execute(sql_text, a=topic_id, b='notifications_script', c=change_type, d=change_log_item).fetchone()

    mail_id = raw_data[0]
    logging.info(f'mailing_id = {mail_id}')

    users_should_not_be_informed = get_from_sql_list_of_users_with_prepared_message(conn, change_log_item)
    logging.info('users_who_should_not_be_informed:')
    logging.info(users_should_not_be_informed)
    logging.info('in total ' + str(len(users_should_not_be_informed)))

    # TODO: do we need this table at all?
    # record into SQL table notif_mailings_status
    sql_text = sqlalchemy.text("""
                                        INSERT INTO notif_mailing_status (mailing_id, event, event_timestamp)
                                        VALUES (:a, :b, :c);
                                        """)
    conn.execute(sql_text, a=mail_id, b='created', c=datetime.datetime.now())

    return users_should_not_be_informed, record_was_processed_already, mail_id


def check_if_age_requirements_met(search_ages, user_ages):
    """check if user wants to receive notifications for such age"""

    requirements_met = False

    if not user_ages or not search_ages:
        return True

    for age_rage in user_ages:
        user_age_range_start = age_rage[0]
        user_age_range_finish = age_rage[1]

        for i in range(user_age_range_start, user_age_range_finish + 1):
            for j in range(search_ages[0], search_ages[1] + 1):
                if i == j:
                    requirements_met = True
                    break
            else:
                continue
            break

    return requirements_met


def crop_user_list(conn: sqlalchemy.engine.Connection, users_list_incoming, users_should_not_be_informed, record):
    """crop user_list to only affected users"""

    users_list_outcome = users_list_incoming

    # 1. INFORG 2X notifications. crop the list of users, excluding Users who receives all types of notifications
    # (otherwise it will be doubling for them)
    temp_user_list = []
    if record.change_type != 4:
        logging.info(f'User List crop due to Inforg 2x: {len(users_list_outcome)} --> {len(users_list_outcome)}')
    else:
        for user_line in users_list_outcome:
            # if this record is about inforg_comments and user already subscribed to all comments
            if not user_line.all_notifs:
                temp_user_list.append(user_line)
                logging.info(
                    f'Inforg 2x CHECK for {user_line.user_id} is OK, record {record.change_type}, '
                    f'user {user_line.user_id} {user_line.all_notifs}. '
                    f'record {record.forum_search_num}'
                )
            else:
                logging.info(
                    f'Inforg 2x CHECK for {user_line.user_id} is FAILED, record {record.change_type}, '
                    f'user {user_line.user_id} {user_line.all_notifs}. '
                    f'record {record.forum_search_num}'
                )
        logging.info(f'User List crop due to Inforg 2x: {len(users_list_outcome)} --> {len(temp_user_list)}')
        users_list_outcome = temp_user_list

    # 2. AGES. crop the list of users, excluding Users who does not want to receive notifications for such Ages
    temp_user_list = []
    if not (record.age_min or record.age_max):
        logging.info('User List crop due to ages: no changes, there were no age_min and max for search')
        return users_list_outcome

    search_age_range = [record.age_min, record.age_max]

    for user_line in users_list_outcome:
        user_age_ranges = user_line.age_periods
        age_requirements_met = check_if_age_requirements_met(search_age_range, user_age_ranges)
        if age_requirements_met:
            temp_user_list.append(user_line)
            logging.info(
                f'AGE CHECK for {user_line.user_id} is OK, record {search_age_range}, '
                f'user {user_age_ranges}. record {record.forum_search_num}'
            )
        else:
            logging.info(
                f'AGE CHECK for {user_line.user_id} is FAIL, record {search_age_range}, '
                f'user {user_age_ranges}. record {record.forum_search_num}'
            )

    logging.info(f'User List crop due to ages: {len(users_list_outcome)} --> {len(temp_user_list)}')
    users_list_outcome = temp_user_list

    # 3. RADIUS. crop the list of users, excluding Users who does want to receive notifications within the radius
    try:
        search_lat = record.search_latitude
        search_lon = record.search_longitude
        list_of_city_coords = None
        if record.city_locations and record.city_locations != 'None':
            non_geolocated = [x for x in eval(record.city_locations) if isinstance(x, str)]
            list_of_city_coords = eval(record.city_locations) if not non_geolocated else None

        temp_user_list = []

        # CASE 3.1. When exact coordinates of Search Headquarters are indicated
        if search_lat and search_lon:
            for user_line in users_list_outcome:
                if not (user_line.radius and user_line.user_latitude and user_line.user_longitude):
                    temp_user_list.append(user_line)
                    continue
                user_lat = user_line.user_latitude
                user_lon = user_line.user_longitude
                actual_distance, direction = define_dist_and_dir_to_search(search_lat, search_lon, user_lat, user_lon)
                actual_distance = int(actual_distance)
                if actual_distance <= user_line.radius:
                    temp_user_list.append(user_line)

        # CASE 3.2. When exact coordinates of a Place are geolocated
        elif list_of_city_coords:
            for user_line in users_list_outcome:
                if not (user_line.radius and user_line.user_latitude and user_line.user_longitude):
                    temp_user_list.append(user_line)
                    continue
                user_lat = user_line.user_latitude
                user_lon = user_line.user_longitude

                for city_coords in list_of_city_coords:
                    search_lat, search_lon = city_coords
                    actual_distance, direction = define_dist_and_dir_to_search(
                        search_lat, search_lon, user_lat, user_lon
                    )
                    actual_distance = int(actual_distance)
                    if actual_distance <= user_line.radius:
                        temp_user_list.append(user_line)
                        break

        # CASE 3.3. No coordinates available
        else:
            temp_user_list = users_list_outcome

        logging.info(f'User List crop due to radius: {len(users_list_outcome)} --> {len(temp_user_list)}')
        users_list_outcome = temp_user_list

    except Exception as e:
        logging.info(f'TEMP - exception radius: {repr(e)}')
        logging.exception(e)

    # 4. DOUBLING. crop the list of users, excluding Users who were already notified on this change_log_id
    temp_user_list = []
    for user_line in users_list_outcome:
        if user_line.user_id not in users_should_not_be_informed:
            temp_user_list.append(user_line)
    logging.info(f'User List crop due to doubling: {len(users_list_outcome)} --> {len(temp_user_list)}')
    users_list_outcome = temp_user_list

    # 5. FOLLOW SEARCH. crop the list of users, excluding Users who is not following this search
    logging.info(f'Crop user list step 5: forum_search_num=={record.forum_search_num}')
    try:
        temp_user_list = []
        sql_text_ = sqlalchemy.text("""
        SELECT u.user_id FROM users u
        LEFT JOIN user_pref_search_filtering upsf ON upsf.user_id=u.user_id and 'whitelist' = ANY(upsf.filter_name)
        WHERE upsf.filter_name is not null AND NOT
        (
            (	exists(select 1 from user_pref_search_whitelist upswls
                    JOIN searches s ON search_forum_num=upswls.search_id 
                    WHERE upswls.user_id=u.user_id and upswls.search_id != :a and upswls.search_following_mode=:b
                    and s.status != 'СТОП')
                AND
                not exists(select 1 from user_pref_search_whitelist upswls WHERE upswls.user_id=u.user_id and upswls.search_id = :a and upswls.search_following_mode=:b)
            ) 
            OR
            exists(select 1 from user_pref_search_whitelist upswls WHERE upswls.user_id=u.user_id and upswls.search_id = :a and upswls.search_following_mode=:c)
        )
        OR upsf.filter_name is null
        ;
        """)
        rows = conn.execute(sql_text_, a=record.forum_search_num, b='👀 ', c='❌ ').fetchall()
        logging.info(f'Crop user list step 5: len(rows)=={len(rows)}')

        users_following = []
        for row in rows:
            users_following.append(row[0])

        temp_user_list = []
        for user_line in users_list_outcome:
            if user_line.user_id in users_following:
                temp_user_list.append(user_line)

        logging.info(
            f'Crop user list step 5: User List crop due to whitelisting: {len(users_list_outcome)} --> {len(temp_user_list)}'
        )
        # if len(users_list_outcome) - len(temp_user_list) <=20:
        #     logging.info(f'Crop user list step 5: cropped users: {users_list_outcome - temp_user_list}')
        users_list_outcome = temp_user_list
    except Exception as ee:
        logging.info('exception happened')
        logging.exception(ee)

    return users_list_outcome


def record_notification_statistics(conn: sqlalchemy.engine.Connection) -> None:
    """records +1 into users' statistics of new searches notification. needed only for usability tips"""

    global stat_list_of_recipients

    dict_of_user_and_number_of_new_notifs = {i: stat_list_of_recipients.count(i) for i in stat_list_of_recipients}

    try:
        for user_id in dict_of_user_and_number_of_new_notifs:
            number_to_add = dict_of_user_and_number_of_new_notifs[user_id]

            sql_text = sqlalchemy.text("""
            INSERT INTO user_stat (user_id, num_of_new_search_notifs)
            VALUES(:a, :b)
            ON CONFLICT (user_id) DO
            UPDATE SET num_of_new_search_notifs = :b +
            (SELECT num_of_new_search_notifs from user_stat WHERE user_id = :a)
            WHERE user_stat.user_id = :a;
            """)
            conn.execute(sql_text, a=int(user_id), b=int(number_to_add))

    except Exception as e:
        logging.error('Recording statistics in notification script failed' + repr(e))
        logging.exception(e)


def iterate_over_all_users(
    conn: sqlalchemy.engine.Connection, admins_list, new_record: LineInChangeLog, list_of_users, function_id
) -> LineInChangeLog:
    """initiates a full cycle for all messages composition for all the users"""
    global stat_list_of_recipients

    stat_list_of_recipients = []  # still not clear why w/o it – saves data from prev iterations
    number_of_situations_checked = 0
    number_of_messages_sent = 0

    try:
        # skip ignored lines which don't require a notification
        if new_record.ignore == 'y':
            new_record.processed = 'yes'
            logging.info('Iterations over all Users and Updates are done (record Ignored)')
            return new_record

        topic_id = new_record.forum_search_num
        change_type = new_record.change_type
        change_log_id = new_record.change_id

        users_who_should_not_be_informed, this_record_was_processed_already, mailing_id = process_mailing_id(
            conn, change_log_id, topic_id, change_type
        )

        list_of_users = crop_user_list(conn, list_of_users, users_who_should_not_be_informed, new_record)

        message_for_pubsub = {'triggered_by_func_id': function_id, 'text': 'initiate notifs send out'}
        publish_to_pubsub(Topics.topic_to_send_notifications, message_for_pubsub)

        for user in list_of_users:
            number_of_situations_checked += 1
            iterate_users_generate_one_notification(
                conn,
                new_record,
                number_of_messages_sent,
                users_who_should_not_be_informed,
                this_record_was_processed_already,
                mailing_id,
                user,
            )

        # mark this line as all-processed
        new_record.processed = 'yes'
        logging.info('Iterations over all Users and Updates are done')

    except Exception as e1:
        logging.info('Not able to Iterate over all Users and Updates: ')
        logging.exception(e1)

    return new_record


def iterate_users_generate_one_notification(
    conn: sqlalchemy.engine.Connection,
    new_record: LineInChangeLog,
    number_of_messages_sent,
    users_who_should_not_be_informed,
    this_record_was_processed_already,
    mailing_id,
    user: User,
):
    change_type = new_record.change_type
    change_log_id = new_record.change_id

    s_lat = new_record.search_latitude
    s_lon = new_record.search_longitude
    topic_type_id = new_record.topic_type_id
    region_to_show = new_record.region if user.user_in_multi_folders else None
    message = ''

    # define if user received this message already
    this_user_was_notified = False
    if this_record_was_processed_already:
        this_user_was_notified = get_from_sql_if_was_notified_already(conn, user.user_id, 'text', new_record.change_id)

        logging.info(f'this user was notified already {user.user_id}, {this_user_was_notified}')
        if user.user_id in users_who_should_not_be_informed:
            logging.info('this user is in the list of non-notifiers')
        else:
            logging.info('this user is NOT in the list of non-notifiers')
    if this_user_was_notified:
        return

    # start composing individual messages (specific user on specific situation)
    if change_type == 0:  # new topic: new search, new event
        if topic_type_id in {0, 1, 2, 3, 4, 5}:  # if it's a new search
            message = compose_individual_message_on_new_search(new_record, user, region_to_show)
        else:  # new event
            message = new_record.message[0]

    elif change_type == 1 and topic_type_id in {0, 1, 2, 3, 4, 5}:  # search status change
        message = new_record.message[0]
        if user.user_in_multi_folders and new_record.message[1]:
            message += new_record.message[1]

    elif change_type == 2:  # 'title_change':
        message = new_record.message

    elif change_type == 3:  # 'replies_num_change':
        message = new_record.message[0]

    elif change_type == 4:  # 'inforg_replies':
        message = new_record.message[0]
        if user.user_in_multi_folders and new_record.message[1]:
            message += new_record.message[1]
        if new_record.message[2]:
            message += new_record.message[2]

    elif change_type == 8:  # first_post_change
        message = compose_individual_message_on_first_post_change(new_record, region_to_show)

    if not message:
        return

    # TODO: to delete msg_group at all ?
    # messages followed by coordinates (sendMessage + sendLocation) have same group
    msg_group_id = get_the_new_group_id(conn) if change_type in {0, 8} else None
    # not None for new_search, field_trips_new, field_trips_change,  coord_change

    number_of_messages_sent += 1  # TODO move out;

    # TODO: make text more compact within 50 symbols
    message_without_html = re.sub(CLEANER_RE, '', message)

    message_params = {'parse_mode': 'HTML', 'disable_web_page_preview': 'True'}

    # for the new searches we add a link to web_app map
    if change_type == 0:
        map_button = {'text': 'Смотреть на Карте Поисков', 'web_app': {'url': get_app_config().web_app_url}}
        message_params['reply_markup'] = {'inline_keyboard': [[map_button]]}

        # record into SQL table notif_by_user
    save_to_sql_notif_by_user(
        conn,
        mailing_id,
        user.user_id,
        message,
        message_without_html,
        'text',
        message_params,
        msg_group_id,
        change_log_id,
    )

    # for user tips in "new search" notifs – to increase sent messages counter
    if change_type == 0 and topic_type_id in {0, 1, 2, 3, 4, 5}:  # 'new_search':
        stat_list_of_recipients.append(user.user_id)

        # save to SQL the sendLocation notification for "new search"
    if change_type in {0} and topic_type_id in {0, 1, 2, 3, 4, 5} and s_lat and s_lon:
        # 'new_search',
        message_params = {'latitude': s_lat, 'longitude': s_lon}

        # record into SQL table notif_by_user (not text, but coords only)
        save_to_sql_notif_by_user(
            conn,
            mailing_id,
            user.user_id,
            None,
            None,
            'coords',
            message_params,
            msg_group_id,
            change_log_id,
        )
    if change_type == 8:
        try:
            list_of_coords = re.findall(r'<code>', message)
            if list_of_coords and len(list_of_coords) == 1:
                # that would mean that there's only 1 set of new coordinates and hence we can
                # send the dedicated sendLocation message
                both_coordinates = re.search(r'(?<=<code>).{5,100}(?=</code>)', message).group()
                if both_coordinates:
                    new_lat = re.search(r'^[\d.]{2,12}(?=\D)', both_coordinates).group()
                    new_lon = re.search(r'(?<=\D)[\d.]{2,12}$', both_coordinates).group()
                    message_params = {'latitude': new_lat, 'longitude': new_lon}
                    save_to_sql_notif_by_user(
                        conn,
                        mailing_id,
                        user.user_id,
                        None,
                        None,
                        'coords',
                        message_params,
                        msg_group_id,
                        change_log_id,
                    )
        except Exception as ee:
            logging.info('exception happened')
            logging.exception(ee)


def generate_yandex_maps_place_link2(lat, lon, param):
    """generate a link to yandex map with lat/lon"""

    display = 'Карта' if param == 'map' else param
    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

    return msg


def compose_individual_message_on_new_search(new_record: LineInChangeLog, user: User, region_to_show):
    """compose individual message for notification of every user on new search"""

    s_lat = new_record.search_latitude
    s_lon = new_record.search_longitude
    u_lat = user.user_latitude
    u_lon = user.user_longitude
    num_of_sent = user.user_new_search_notifs

    place_link = ''
    clickable_coords = ''
    tip_on_click_to_copy = ''
    tip_on_home_coords = ''

    region_wording = f' в регионе {region_to_show}' if region_to_show else ''

    # 0. Heading and Region clause if user is 'multi-regional'
    message = f'{new_record.topic_emoji}Новый поиск{region_wording}!\n'

    # 1. Search important attributes - common part (e.g. 'Внимание, выезд!)
    if new_record.message[1]:
        message += new_record.message[1]

    # 2. Person (e.g. 'Иванов 60' )
    message += '\n' + new_record.message[0]

    # 3. Dist & Dir – individual part for every user
    if s_lat and s_lon and u_lat and u_lon:
        try:
            dist, direct = define_dist_and_dir_to_search(s_lat, s_lon, u_lat, u_lon)
            dist = int(dist)
            direction = f'\n\nОт вас ~{dist} км {direct}'

            message += generate_yandex_maps_place_link2(s_lat, s_lon, direction)
            message += f'\n<code>{COORD_FORMAT.format(float(s_lat))}, ' f'{COORD_FORMAT.format(float(s_lon))}</code>'

        except Exception as e:
            logging.info(
                f'Not able to compose individual msg with distance & direction, params: '
                f'[{new_record}, {s_lat}, {s_lon}, {u_lat}, {u_lon}]'
            )
            logging.exception(e)

    if s_lat and s_lon and not u_lat and not u_lon:
        try:
            message += '\n\n' + generate_yandex_maps_place_link2(s_lat, s_lon, 'map')

        except Exception as e:
            logging.info(
                f'Not able to compose message with Yandex Map Link, params: '
                f'[{new_record}, {s_lat}, {s_lon}, {u_lat}, {u_lon}]'
            )
            logging.exception(e)

    # 4. Managers – common part
    if new_record.message[2]:
        message += '\n\n' + new_record.message[2]

    message += '\n\n'

    # 5. Tips and Suggestions
    if not num_of_sent or num_of_sent in fib_list:
        if s_lat and s_lon:
            message += '<i>Совет: Координаты и телефоны можно скопировать, нажав на них.</i>\n'

        if s_lat and s_lon and not u_lat and not u_lon:
            message += (
                '<i>Совет: Чтобы Бот показывал Направление и Расстояние до поиска – просто укажите ваши '
                '"Домашние координаты" в Настройках Бота.</i>'
            )

    if s_lat and s_lon:
        clickable_coords = f'<code>{COORD_FORMAT.format(float(s_lat))}, {COORD_FORMAT.format(float(s_lon))}</code>'
        if u_lat and u_lon:
            dist, direct = define_dist_and_dir_to_search(s_lat, s_lon, u_lat, u_lon)
            dist = int(dist)
            place = f'От вас ~{dist} км {direct}'
        else:
            place = 'Карта'
        place_link = f'<a href="https://yandex.ru/maps/?pt={s_lon},{s_lat}&z=11&l=map">{place}</a>'

        if not num_of_sent or num_of_sent in fib_list:
            tip_on_click_to_copy = '<i>Совет: Координаты и телефоны можно скопировать, нажав на них.</i>'
            if not u_lat and not u_lon:
                tip_on_home_coords = (
                    '<i>Совет: Чтобы Бот показывал Направление и Расстояние до поиска – просто '
                    'укажите ваши "Домашние координаты" в Настройках Бота.</i>'
                )

    # TODO - yet not implemented new message template
    obj = new_record.message_object
    final_message = f"""{new_record.topic_emoji}Новый поиск{region_wording}!\n
                        {obj.activities}\n\n
                        {obj.clickable_name}\n\n
                        {place_link}\n
                        {clickable_coords}\n\n
                        {obj.managers}\n\n
                        {tip_on_click_to_copy}\n\n
                        {tip_on_home_coords}"""

    final_message = re.sub(r'\s{3,}', '\n\n', final_message)  # clean excessive blank lines
    final_message = re.sub(r'\s*$', '', final_message)  # clean blank symbols in the end of file
    logging.info(f'OLD - FINAL NEW MESSAGE FOR NEW SEARCH: {message}')
    logging.info(f'NEW - FINAL NEW MESSAGE FOR NEW SEARCH: {final_message}')
    # TODO ^^^

    return message


def compose_individual_message_on_first_post_change(new_record: LineInChangeLog, region_to_show):
    """compose individual message for notification of every user on change of first post"""

    message = new_record.message
    region = f' ({region_to_show})' if region_to_show else ''
    message = message.format(region=region)

    return message


def mark_new_record_as_processed(conn: sqlalchemy.engine.Connection, new_record: LineInChangeLog):
    """mark all the new records in SQL as processed, to avoid processing in the next iteration"""

    try:
        if new_record.processed == 'yes':
            if new_record.ignore != 'y':
                sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'y' WHERE id=:a;""")
                conn.execute(sql_text, a=new_record.change_id)
                logging.info(f'The New Record {new_record.change_id} was marked as processed in PSQL')
            else:
                sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'n' WHERE id=:a;""")
                conn.execute(sql_text, a=new_record.change_id)
                logging.info(f'The New Record {new_record.change_id} was marked as IGNORED in PSQL')

        logging.info('All Updates are marked as processed in Change Log')

    except Exception as e:
        # FIXME – should be a smarter way to re-process the record instead of just marking everything as processed
        # For Safety's Sake – Update Change_log SQL table, setting 'y' everywhere
        conn.execute(
            """UPDATE change_log SET notification_sent = 'y' WHERE notification_sent is NULL
            OR notification_sent='s';"""
        )

        logging.info('Not able to mark Updates as Processed in Change Log')
        logging.exception(e)
        logging.info('Due to error, all Updates are marked as processed in Change Log')
        notify_admin('ERROR: Not able to mark Updates as Processed in Change Log!')
        # FIXME ^^^

    return None


def mark_new_comments_as_processed(conn: sqlalchemy.engine.Connection, record: LineInChangeLog) -> None:
    """mark in SQL table Comments all the comments that were processed at this step, basing on search_forum_id"""

    try:
        # TODO – is it correct that we mark comments processes for any Comments for certain search? Looks
        #  like we can mark some comments which are not yet processed at all. Probably base on change_id? To be checked
        if record.processed == 'yes' and record.ignore != 'y':
            if record.change_type == 3:
                sql_text = sqlalchemy.text("UPDATE comments SET notification_sent = 'y' WHERE search_forum_num=:a;")
                conn.execute(sql_text, a=record.forum_search_num)

            elif record.change_type == 4:
                sql_text = sqlalchemy.text("UPDATE comments SET notif_sent_inforg = 'y' WHERE search_forum_num=:a;")
                conn.execute(sql_text, a=record.forum_search_num)
            # FIXME ^^^

            logging.info(f'The Update {record.change_id} with Comments that are processed and not ignored')
            logging.info('All Comments are marked as processed')

    except Exception as e:
        # TODO – seems a vary vague solution: to mark all
        sql_text = sqlalchemy.text("""UPDATE comments SET notification_sent = 'y' WHERE notification_sent is Null
                                      OR notification_sent = 's';""")
        conn.execute(sql_text)
        sql_text = sqlalchemy.text("""UPDATE comments SET notif_sent_inforg = 'y' WHERE notif_sent_inforg is Null;""")
        conn.execute(sql_text)

        logging.info('Not able to mark Comments as Processed:')
        logging.exception(e)
        logging.info('Due to error, all Comments are marked as processed')
        notify_admin('ERROR: Not able to mark Comments as Processed!')
        # TODO ^^^




def check_if_need_compose_more(conn: sqlalchemy.engine.Connection, function_id: int):
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

    return None


def delete_ended_search_following(conn: Connection, new_record: LineInChangeLog) -> None:  # issue425
    ### Delete from user_pref_search_whitelist if the search goes to one of ending statuses

    if new_record.change_type == 1 and new_record.status in ['Завершен', 'НЖ', 'НП', 'Найден']:
        stmt = sqlalchemy.text("""DELETE FROM user_pref_search_whitelist WHERE search_id=:a;""")
        conn.execute(stmt, a=new_record.forum_search_num)
        logging.info(
            f'Search id={new_record.forum_search_num} with status {new_record.status} is been deleted from user_pref_search_whitelist.'
        )
    return None


def main(event, context):  # noqa
    """key function which is initiated by Pub/Sub"""

    analytics_start_of_func = datetime.datetime.now()

    function_id = generate_random_function_id()
    message_from_pubsub = process_pubsub_message_v2(event)
    triggered_by_func_id = get_triggering_function(message_from_pubsub)

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

    pool = sql_connect()
    with pool.connect() as conn:
        # compose New Records List: the delta from Change log
        new_record = compose_new_records_from_change_log(conn)

        # only if there are updates in Change Log
        if new_record:
            delete_ended_search_following(conn, new_record)  # issue425
            # enrich New Records List with all the updates that should be in notifications
            new_record = enrich_new_record_from_searches(conn, new_record)
            new_record = enrich_new_record_with_search_activities(conn, new_record)
            new_record = enrich_new_record_with_managers(conn, new_record)
            new_record = enrich_new_record_with_comments(conn, 'all', new_record)
            new_record = enrich_new_record_with_comments(conn, 'inforg', new_record)
            new_record = enrich_new_record_with_clickable_name(new_record)
            new_record = enrich_new_record_with_emoji(new_record)
            new_record = enrich_new_record_with_com_message_texts(new_record)

            # compose Users List: all the notifications recipients' details
            admins_list, testers_list = get_list_of_admins_and_testers(conn)  # for debug purposes
            list_of_users = compose_users_list_from_users(conn, new_record)
            list_of_users = enrich_users_list_with_age_periods(conn, list_of_users)
            list_of_users = enrich_users_list_with_radius(conn, list_of_users)

            analytics_match_finish = datetime.datetime.now()
            duration_match = round((analytics_match_finish - analytics_start_of_func).total_seconds(), 2)
            logging.info(f'time: function match end-to-end – {duration_match} sec')

            # check the matrix: new update - user and initiate sending notifications
            new_record = iterate_over_all_users(conn, admins_list, new_record, list_of_users, function_id)

            analytics_iterations_finish = datetime.datetime.now()
            duration_iterations = round((analytics_iterations_finish - analytics_match_finish).total_seconds(), 2)
            logging.info(f'time: function iterations end-to-end – {duration_iterations} sec')

            # mark all the "new" lines in tables Change Log & Comments as "old"
            mark_new_record_as_processed(conn, new_record)
            mark_new_comments_as_processed(conn, new_record)

            # final step – update statistics on how many users received notifications on new searches
            record_notification_statistics(conn)

        check_if_need_compose_more(conn, function_id)

        list_of_change_log_ids = []
        if new_record:
            try:
                list_of_change_log_ids = [new_record.change_id]
            except Exception as e:  # noqa
                logging.exception(e)

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

    pool.dispose()
