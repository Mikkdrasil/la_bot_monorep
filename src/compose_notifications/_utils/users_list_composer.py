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
        self.enrich_users_list_with_age_periods(list_of_users)
        self.enrich_users_list_with_radius(list_of_users)

        return list_of_users

    def enrich_users_list_with_age_periods(self, list_of_users: list[User]) -> None:
        """add the data on Lost people age notification preferences from user_pref_age into users List"""

        try:
            notif_prefs = self.conn.execute("""SELECT user_id, period_min, period_max FROM user_pref_age;""").fetchall()

            if not notif_prefs:
                return

            number_of_enrichments_old = 0
            number_of_enrichments = 0
            for np_line in notif_prefs:
                new_period = [np_line[1], np_line[2]]

                for u_line in list_of_users:
                    if u_line.user_id == np_line[0]:
                        u_line.age_periods.append(new_period)
                        number_of_enrichments += 1

            logging.info(f'Users List enriched with Age Prefs, OLD num of enrichments is {number_of_enrichments_old}')
            logging.info(f'Users List enriched with Age Prefs, num of enrichments is {number_of_enrichments}')

        except Exception as e:
            logging.info('Not able to enrich Users List with Age Prefs')
            logging.exception(e)

    def enrich_users_list_with_radius(self, list_of_users: list[User]) -> None:
        """add the data on distance notification preferences from user_pref_radius into users List"""

        try:
            notif_prefs = self.conn.execute("""SELECT user_id, radius FROM user_pref_radius;""").fetchall()

            if not notif_prefs:
                return None

            number_of_enrichments = 0
            for np_line in notif_prefs:
                for u_line in list_of_users:
                    if u_line.user_id == np_line[0]:
                        u_line.radius = int(round(np_line[1], 0))
                        number_of_enrichments += 1
                        print(f'TEMP - RADIUS user_id = {u_line.user_id}, radius = {u_line.radius}')

            logging.info(f'Users List enriched with Radius, num of enrichments is {number_of_enrichments}')

        except Exception as e:
            logging.info('Not able to enrich Users List with Radius')
            logging.exception(e)

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
                /*action='get_user_list_filtered_by_folder_and_notif_type' */;
                                           """)

            users_short_version = self.conn.execute(
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
