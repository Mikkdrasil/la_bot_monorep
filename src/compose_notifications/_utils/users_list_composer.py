import datetime
import logging

import sqlalchemy
from sqlalchemy.engine.base import Connection

from .notif_common import LineInChangeLog, User


class UsersListComposer:
    def __init__(self, conn: Connection):
        self.conn = conn

    def get_users_list_for_line_in_change_log(self, new_record: LineInChangeLog) -> list[User]:
        list_of_users = self.compose_users_list_from_users(new_record)

        return list_of_users

    def compose_users_list_from_users(self, new_record: LineInChangeLog) -> list[User]:
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
                    ---
                    user_notif_pref_prep AS (
                        SELECT user_id, array_agg(pref_id) AS agg
                        FROM user_preferences GROUP BY user_id),
                    ---
                    user_notif_type_pref AS (
                        SELECT user_id, CASE WHEN 30 = ANY(agg) THEN True ELSE False END AS all_notifs
                        FROM user_notif_pref_prep
                        WHERE (30 = ANY(agg) OR :change_type = ANY(agg))
                            AND NOT (4 = ANY(agg)  /* 4 is topic_inforg_comment_new */
                            AND :change_type = 2)), /* 2 is topic_title_change */ /*AK20240409:issue13*/
                    ---
                    user_folders_prep AS (
                        SELECT user_id, forum_folder_num,
                            CASE WHEN count(forum_folder_num) OVER (PARTITION BY user_id) > 1
                                THEN TRUE ELSE FALSE END as multi_folder
                        FROM user_regional_preferences),
                    ---
                    user_folders AS (
                        SELECT user_id, forum_folder_num, multi_folder
                        FROM user_folders_prep WHERE forum_folder_num= :forum_folder),
                    ---
                    user_topic_pref_prep AS (
                        SELECT user_id, array_agg(topic_type_id) aS agg
                        FROM user_pref_topic_type GROUP BY user_id),
                    ---
                    user_topic_type_pref AS (
                        SELECT user_id, agg AS all_types
                        FROM user_topic_pref_prep
                        WHERE 30 = ANY(agg) OR :topic_type_id = ANY(agg)),
                    ---
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
                    ---
                    user_with_loc AS (
                        SELECT u.user_id, u.username_telegram, uc.latitude, uc.longitude,
                            u.role, u.multi_folder, u.all_notifs
                        FROM user_short_list AS u
                        LEFT JOIN user_coordinates as uc
                        ON u.user_id=uc.user_id),
                    ---
                    user_age_prefs AS (
                        SELECT user_id, array_agg(array[period_min, period_max]) as age_prefs 
                        FROM user_pref_age 
                        GROUP BY user_id)
                ----------------------------------------------------------------
                SELECT  ns.user_id, ns.username_telegram, ns.latitude, ns.longitude, ns.role,
                        st.num_of_new_search_notifs, ns.multi_folder, ns.all_notifs, 
                        upr.radius, uap.age_prefs
                FROM user_with_loc AS ns
                LEFT JOIN user_stat st
                    ON ns.user_id=st.user_id
                LEFT JOIN user_pref_radius upr
                    ON ns.user_id=upr.user_id
                LEFT JOIN user_age_prefs AS uap
                    ON ns.user_id=uap.user_id
                -----
                /*action='get_user_list_filtered_by_folder_and_notif_type' */;
                                           """)

            users_short_version = self.conn.execute(
                sql_text_psy,
                change_type=new_record.change_type,
                forum_folder=new_record.forum_folder,
                topic_type_id=new_record.topic_type_id,
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
                    radius=int(line[8]) if line[8] is not None else 0,
                    age_periods=line[9] if line[9] is not None else [],
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
