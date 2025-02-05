import datetime
import logging

import sqlalchemy
from sqlalchemy.engine.base import Connection

from .notif_common import ChangeType, LineInChangeLog, SearchFollowingMode, User, define_dist_and_dir_to_search


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

    def crop_user_list(
        self,
        users_list_incoming: list[User],
        record: LineInChangeLog,
    ):
        """crop user_list to only affected users
        TODO can we move it to UsersListComposer?"""
        filterer = UserListFilter(self.conn, record, users_list_incoming)
        users_list_outcome = filterer.apply()

        return users_list_outcome


def check_if_age_requirements_met(search_ages: tuple[int | None, int | None], user_ages: list[tuple[int, int]]) -> bool:
    """check if user wants to receive notifications for such age"""

    if not user_ages or search_ages[0] is None or search_ages[1] is None:
        return True

    for age_range in user_ages:
        if (min(*age_range) <= max(search_ages[0], search_ages[1])) and (
            max(*age_range) >= min(search_ages[0], search_ages[1])
        ):
            return True
    return False


class UserListFilter:
    def __init__(self, conn: Connection, new_record: LineInChangeLog, users: list[User]):
        self.conn = conn
        self.new_record = new_record
        self.users = users.copy()

    def apply(self) -> list[User]:
        self.users = self._filter_inforg_double_notification_for_users()
        self.users = self._filter_users_by_age_settings()
        self.users = self._filter_users_by_search_radius()
        self.users = self._filter_users_with_prepared_messages()
        self.users = self._filter_users_not_following_this_search()

        return self.users

    def _filter_inforg_double_notification_for_users(self) -> list[User]:
        # 1. INFORG 2X notifications. crop the list of users, excluding Users who receives all types of notifications
        # (otherwise it will be doubling for them)
        record = self.new_record
        users_list_outcome = self.users
        temp_user_list: list[User] = []
        if record.change_type != ChangeType.topic_inforg_comment_new:
            logging.info(f'User List crop due to Inforg 2x: {len(users_list_outcome)} --> {len(users_list_outcome)}')
            return users_list_outcome
        else:
            for user_line in users_list_outcome:
                # if this record is about inforg_comments and user already subscribed to all comments
                check_passed = not user_line.all_notifs
                logging.info(
                    f'Inforg 2x CHECK for {user_line.user_id} is {"OK" if check_passed else "FAIL"}, record {record.change_type}, '
                    f'user {user_line.user_id} {user_line.all_notifs}. '
                    f'record {record.forum_search_num}'
                )
                if check_passed:
                    temp_user_list.append(user_line)
            logging.info(f'User List crop due to Inforg 2x: {len(users_list_outcome)} --> {len(temp_user_list)}')
        return temp_user_list

    def _filter_users_by_age_settings(self) -> list[User]:
        # 2. AGES. crop the list of users, excluding Users who does not want to receive notifications for such Ages
        users_list_outcome = self.users
        record = self.new_record
        if not (record.age_min or record.age_max):
            logging.info('User List crop due to ages: no changes, there were no age_min and max for search')
            return users_list_outcome

        temp_user_list: list[User] = []
        search_age_range = (record.age_min, record.age_max)

        for user_line in users_list_outcome:
            age_requirements_met = check_if_age_requirements_met(search_age_range, user_line.age_periods)
            logging.info(
                f'AGE CHECK for {user_line.user_id} is {"OK" if age_requirements_met else "FAIL"}, record {search_age_range}, '
                f'user {user_line.age_periods}. record {record.forum_search_num}'
            )
            if age_requirements_met:
                temp_user_list.append(user_line)

        logging.info(f'User List crop due to ages: {len(users_list_outcome)} --> {len(temp_user_list)}')
        return temp_user_list

    def _filter_users_by_search_radius(self) -> list[User]:
        # 3. RADIUS. crop the list of users, excluding Users who does want to receive notifications within the radius
        record = self.new_record
        users_list_outcome = self.users
        temp_user_list = []
        try:
            search_lat = record.search_latitude
            search_lon = record.search_longitude
            list_of_city_coords = None
            if record.city_locations and record.city_locations != 'None':
                non_geolocated = [x for x in eval(record.city_locations) if isinstance(x, str)]
                list_of_city_coords = eval(record.city_locations) if not non_geolocated else None

            # CASE 3.1. When exact coordinates of Search Headquarters are indicated
            if search_lat and search_lon:
                for user_line in users_list_outcome:
                    if not (user_line.radius and user_line.user_latitude and user_line.user_longitude):
                        temp_user_list.append(user_line)
                        continue
                    user_lat = user_line.user_latitude
                    user_lon = user_line.user_longitude
                    actual_distance, direction = define_dist_and_dir_to_search(
                        search_lat, search_lon, user_lat, user_lon
                    )
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
                        if not search_lat or not search_lon:
                            continue
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

        except Exception as e:
            logging.info(f'TEMP - exception radius: {repr(e)}')
            logging.exception(e)
        return temp_user_list

    def _filter_users_with_prepared_messages(self) -> list[User]:
        # 4. DOUBLING. crop the list of users, excluding Users who were already notified on this change_log_id
        # TODO do we still need it?
        users_list_outcome = self.users
        users_with_prepared_messages = self._get_from_sql_list_of_users_with_prepared_message()
        temp_user_list = [user for user in users_list_outcome if user.user_id not in users_with_prepared_messages]
        logging.info(f'User List crop due to doubling: {len(users_list_outcome)} --> {len(temp_user_list)}')
        return temp_user_list

    def _filter_users_not_following_this_search(self) -> list[User]:
        # 5. FOLLOW SEARCH. crop the list of users, excluding Users who is not following this search
        users_list_outcome = self.users
        record = self.new_record
        logging.info(f'Crop user list step 5: forum_search_num=={record.forum_search_num}')
        temp_user_list: list[User] = []
        sql_text_ = sqlalchemy.text("""
            SELECT u.user_id FROM users u
            LEFT JOIN user_pref_search_filtering upsf 
                ON upsf.user_id=u.user_id and 'whitelist' = ANY(upsf.filter_name)
            WHERE 
                upsf.filter_name is not null AND NOT
            (
                (	exists(
                            -- user following any other active (not stopped) search
                            select 1 FROM user_pref_search_whitelist upswls
                            JOIN searches s ON search_forum_num=upswls.search_id 
                            WHERE 
                                upswls.user_id=u.user_id 
                                and upswls.search_id != :forum_search_num 
                                and upswls.search_following_mode=:following_mode_on
                                and s.status != 'СТОП'
                            )
                    AND
                    not exists(
                            -- user following this search
                            select 1 from user_pref_search_whitelist upswls 
                            WHERE 
                                upswls.user_id=u.user_id 
                                and upswls.search_id = :forum_search_num 
                                and upswls.search_following_mode=:following_mode_on
                                )
                ) 
                OR exists(
                        -- user stopped following this search
                        select 1 from user_pref_search_whitelist upswls 
                        WHERE 
                            upswls.user_id=u.user_id 
                            and upswls.search_id = :forum_search_num 
                            and upswls.search_following_mode=:following_mode_off
                        )
            )
            OR upsf.filter_name is null
            ;
        """)
        rows = self.conn.execute(
            sql_text_,
            forum_search_num=record.forum_search_num,
            following_mode_on=SearchFollowingMode.ON,
            following_mode_off=SearchFollowingMode.OFF,
        ).fetchall()
        logging.info(f'Crop user list step 5: len(rows)=={len(rows)}')

        following_users_ids = set([row[0] for row in rows])
        temp_user_list = [user for user in users_list_outcome if user.user_id in following_users_ids]

        logging.info(
            f'Crop user list step 5: User List crop due to whitelisting: {len(users_list_outcome)} --> {len(temp_user_list)}'
        )
        return temp_user_list

    def _get_from_sql_list_of_users_with_prepared_message(self) -> set[int]:
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

        raw_data_ = self.conn.execute(sql_text_, a=self.new_record.change_log_id).fetchall()
        # TODO: to delete
        logging.info('list of user with composed messages:')
        logging.info(raw_data_)

        users_who_were_composed = [line[0] for line in raw_data_]

        logging.info('users_who_should_not_be_informed:')
        logging.info(users_who_were_composed)
        logging.info(f'in total {len(users_who_were_composed)}')
        return set(users_who_were_composed)
