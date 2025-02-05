import datetime
import logging
import re

import sqlalchemy
from sqlalchemy.engine.base import Connection

from _dependencies.commons import Topics, get_app_config, publish_to_pubsub
from _dependencies.misc import notify_admin

from .notif_common import COORD_FORMAT, SEARCH_TOPIC_TYPES, LineInChangeLog, User, define_dist_and_dir_to_search

CLEANER_RE = re.compile('<.*?>')

FIB_LIST = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]


class NotificationComposer:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self.stat_list_of_recipients: list[int] = []  # list of users who received notification on new search

    def generate_notifications_for_users(
        self, new_record: LineInChangeLog, list_of_users: list[User], function_id: int
    ):
        """initiates a full cycle for all messages composition for all the users"""

        number_of_situations_checked = 0

        try:
            # skip ignored lines which don't require a notification
            if new_record.ignore:
                new_record.processed = True
                logging.info('Iterations over all Users and Updates are done (record Ignored)')
                return

            topic_id = new_record.forum_search_num
            change_type = new_record.change_type
            change_log_id = new_record.change_log_id

            users_who_should_not_be_informed, this_record_was_processed_already, mailing_id = self.process_mailing_id(
                change_log_id, topic_id, change_type
            )

            list_of_users = self.crop_user_list(list_of_users, users_who_should_not_be_informed, new_record)

            message_for_pubsub = {'triggered_by_func_id': function_id, 'text': 'initiate notifs send out'}
            publish_to_pubsub(Topics.topic_to_send_notifications, message_for_pubsub)

            for user in list_of_users:
                number_of_situations_checked += 1
                self.generate_notification_for_user(
                    new_record,
                    users_who_should_not_be_informed,
                    this_record_was_processed_already,
                    mailing_id,
                    user,
                )

            # mark this line as all-processed
            new_record.processed = True
            logging.info('Iterations over all Users and Updates are done')

        except Exception as e1:
            logging.info('Not able to Iterate over all Users and Updates: ')
            logging.exception(e1)

    def process_mailing_id(self, change_log_id: int, topic_id: int, change_type):
        """TODO"""

        # check if this change_log record was somehow processed
        sql_text = sqlalchemy.text("""SELECT EXISTS (SELECT * FROM notif_mailings WHERE change_log_id=:a);""")
        record_was_processed_already = self.conn.execute(sql_text, a=change_log_id).fetchone()[0]

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
        raw_data = self.conn.execute(
            sql_text, a=topic_id, b='notifications_script', c=change_type, d=change_log_id
        ).fetchone()

        mail_id = raw_data[0]
        logging.info(f'mailing_id = {mail_id}')

        users_should_not_be_informed = self.get_from_sql_list_of_users_with_prepared_message(change_log_id)
        logging.info('users_who_should_not_be_informed:')
        logging.info(users_should_not_be_informed)
        logging.info('in total ' + str(len(users_should_not_be_informed)))

        # TODO: do we need this table at all?
        # record into SQL table notif_mailings_status
        sql_text = sqlalchemy.text("""
                                            INSERT INTO notif_mailing_status (mailing_id, event, event_timestamp)
                                            VALUES (:a, :b, :c);
                                            """)
        self.conn.execute(sql_text, a=mail_id, b='created', c=datetime.datetime.now())

        return users_should_not_be_informed, record_was_processed_already, mail_id

    def get_from_sql_list_of_users_with_prepared_message(self, change_log_id: int) -> list[int]:
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

        raw_data_ = self.conn.execute(sql_text_, a=change_log_id).fetchall()
        # TODO: to delete
        logging.info('list of user with composed messages:')
        logging.info(raw_data_)

        users_who_were_composed = []
        for line in raw_data_:
            users_who_were_composed.append(line[0])

        return users_who_were_composed

    def crop_user_list(
        self,
        users_list_incoming: list[User],
        users_should_not_be_informed,
        record: LineInChangeLog,
    ):
        """crop user_list to only affected users
        TODO can we move it to UsersListComposer?"""

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
        temp_user_list: list[User] = []
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
            rows = self.conn.execute(sql_text_, a=record.forum_search_num, b='👀 ', c='❌ ').fetchall()
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

    def generate_notification_for_user(
        self,
        new_record: LineInChangeLog,
        users_who_should_not_be_informed,
        this_record_was_processed_already,
        mailing_id,
        user: User,
    ):
        change_type = new_record.change_type
        change_log_id = new_record.change_log_id

        s_lat = new_record.search_latitude
        s_lon = new_record.search_longitude
        topic_type_id = new_record.topic_type_id
        region_to_show = new_record.region if user.user_in_multi_folders else None
        user_message = ''

        # define if user received this message already
        if this_record_was_processed_already:
            this_user_was_notified = self.get_from_sql_if_was_notified_already(
                user.user_id, 'text', new_record.change_log_id
            )

            logging.info(f'this user was notified already {user.user_id}, {this_user_was_notified}')
            if user.user_id in users_who_should_not_be_informed:
                logging.info('this user is in the list of non-notifiers')
            else:
                logging.info('this user is NOT in the list of non-notifiers')

            if this_user_was_notified:
                return

        # start composing individual messages (specific user on specific situation)
        user_message = MessageComposer(new_record, user, region_to_show).compose_message_for_user()
        if not user_message:
            return

        # TODO: to delete msg_group at all ?
        # messages followed by coordinates (sendMessage + sendLocation) have same group
        msg_group_id = self.get_the_new_group_id() if change_type in {0, 8} else None
        # not None for new_search, field_trips_new, field_trips_change,  coord_change

        # TODO: make text more compact within 50 symbols
        message_without_html = re.sub(CLEANER_RE, '', user_message)

        message_params = {'parse_mode': 'HTML', 'disable_web_page_preview': 'True'}

        # for the new searches we add a link to web_app map
        if change_type == 0:
            map_button = {'text': 'Смотреть на Карте Поисков', 'web_app': {'url': get_app_config().web_app_url}}
            message_params['reply_markup'] = {'inline_keyboard': [[map_button]]}

            # record into SQL table notif_by_user
        self.save_to_sql_notif_by_user(
            mailing_id,
            user.user_id,
            user_message,
            message_without_html,
            'text',
            message_params,
            msg_group_id,
            change_log_id,
        )

        # for user tips in "new search" notifs – to increase sent messages counter
        if change_type == 0 and topic_type_id in SEARCH_TOPIC_TYPES:  # 'new_search':
            self.stat_list_of_recipients.append(user.user_id)

            # save to SQL the sendLocation notification for "new search"
        if change_type in {0} and topic_type_id in SEARCH_TOPIC_TYPES and s_lat and s_lon:
            # 'new_search',
            message_params = {'latitude': s_lat, 'longitude': s_lon}

            # record into SQL table notif_by_user (not text, but coords only)
            self.save_to_sql_notif_by_user(
                mailing_id,
                user.user_id,
                None,
                None,
                'coords',
                message_params,
                msg_group_id,
                change_log_id,
            )
        elif change_type == 8:
            try:
                list_of_coords = re.findall(r'<code>', user_message)
                if list_of_coords and len(list_of_coords) == 1:
                    # that would mean that there's only 1 set of new coordinates and hence we can
                    # send the dedicated sendLocation message
                    both_coordinates = re.search(r'(?<=<code>).{5,100}(?=</code>)', user_message).group()
                    if both_coordinates:
                        new_lat = re.search(r'^[\d.]{2,12}(?=\D)', both_coordinates).group()
                        new_lon = re.search(r'(?<=\D)[\d.]{2,12}$', both_coordinates).group()
                        message_params = {'latitude': new_lat, 'longitude': new_lon}
                        self.save_to_sql_notif_by_user(
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

    def get_the_new_group_id(self) -> int:
        """define the max message_group_id in notif_by_user and add +1"""

        raw_data_ = self.conn.execute("""SELECT MAX(message_group_id) FROM notif_by_user
        /*action='get_the_new_group_id'*/
        ;""").fetchone()

        if raw_data_[0]:
            next_id = raw_data_[0] + 1
        else:
            next_id = 0

        return next_id

    def get_from_sql_if_was_notified_already(self, user_id_, message_type_, change_log_id_):
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

        user_was_already_notified = self.conn.execute(
            sql_text_, a=change_log_id_, b=user_id_, c=message_type_
        ).fetchone()[0]

        return user_was_already_notified

    def save_to_sql_notif_by_user(
        self,
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

        self.conn.execute(
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

    def record_notification_statistics(self) -> None:
        """records +1 into users' statistics of new searches notification. needed only for usability tips"""

        dict_of_user_and_number_of_new_notifs = {
            i: self.stat_list_of_recipients.count(i) for i in self.stat_list_of_recipients
        }

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
                self.conn.execute(sql_text, a=int(user_id), b=int(number_to_add))

        except Exception as e:
            logging.error('Recording statistics in notification script failed' + repr(e))
            logging.exception(e)

    def mark_new_record_as_processed(self, new_record: LineInChangeLog):
        """mark all the new records in SQL as processed, to avoid processing in the next iteration"""

        try:
            if new_record.processed:
                if not new_record.ignore:
                    sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'y' WHERE id=:a;""")
                    self.conn.execute(sql_text, a=new_record.change_log_id)
                    logging.info(f'The New Record {new_record.change_log_id} was marked as processed in PSQL')
                else:
                    sql_text = sqlalchemy.text("""UPDATE change_log SET notification_sent = 'n' WHERE id=:a;""")
                    self.conn.execute(sql_text, a=new_record.change_log_id)
                    logging.info(f'The New Record {new_record.change_log_id} was marked as IGNORED in PSQL')

            logging.info('All Updates are marked as processed in Change Log')

        except Exception as e:
            # FIXME – should be a smarter way to re-process the record instead of just marking everything as processed
            # For Safety's Sake – Update Change_log SQL table, setting 'y' everywhere
            self.conn.execute(
                """UPDATE change_log SET notification_sent = 'y' WHERE notification_sent is NULL
                OR notification_sent='s';"""
            )

            logging.info('Not able to mark Updates as Processed in Change Log')
            logging.exception(e)
            logging.info('Due to error, all Updates are marked as processed in Change Log')
            notify_admin('ERROR: Not able to mark Updates as Processed in Change Log!')
            # FIXME ^^^

        return None

    def mark_new_comments_as_processed(self, record: LineInChangeLog) -> None:
        """mark in SQL table Comments all the comments that were processed at this step, basing on search_forum_id"""

        try:
            # TODO – is it correct that we mark comments processes for any Comments for certain search? Looks
            #  like we can mark some comments which are not yet processed at all. Probably base on change_id? To be checked
            if record.processed and not record.ignore:
                if record.change_type == 3:
                    sql_text = sqlalchemy.text("UPDATE comments SET notification_sent = 'y' WHERE search_forum_num=:a;")
                    self.conn.execute(sql_text, a=record.forum_search_num)

                elif record.change_type == 4:
                    sql_text = sqlalchemy.text("UPDATE comments SET notif_sent_inforg = 'y' WHERE search_forum_num=:a;")
                    self.conn.execute(sql_text, a=record.forum_search_num)
                # FIXME ^^^

                logging.info(f'The Update {record.change_log_id} with Comments that are processed and not ignored')
                logging.info('All Comments are marked as processed')

        except Exception as e:
            # TODO – seems a vary vague solution: to mark all
            sql_text = sqlalchemy.text("""UPDATE comments SET notification_sent = 'y' WHERE notification_sent is Null
                                        OR notification_sent = 's';""")
            self.conn.execute(sql_text)
            sql_text = sqlalchemy.text(
                """UPDATE comments SET notif_sent_inforg = 'y' WHERE notif_sent_inforg is Null;"""
            )
            self.conn.execute(sql_text)

            logging.info('Not able to mark Comments as Processed:')
            logging.exception(e)
            logging.info('Due to error, all Comments are marked as processed')
            notify_admin('ERROR: Not able to mark Comments as Processed!')


class MessageComposer:
    def __init__(self, new_record: LineInChangeLog, user: User, region_to_show):
        self.new_record = new_record
        self.user = user
        self.region_to_show = region_to_show

    def compose_message_for_user(self) -> str:
        change_type = self.new_record.change_type
        topic_type_id = self.new_record.topic_type_id
        if change_type == 0:  # new topic: new search, new event
            if topic_type_id in SEARCH_TOPIC_TYPES:  # if it's a new search
                message = self._compose_individual_message_on_new_search()
            else:  # new event
                message = self.new_record.message[0]

        elif change_type == 1 and topic_type_id in SEARCH_TOPIC_TYPES:  # search status change
            message = self.new_record.message[0]
            if self.user.user_in_multi_folders and self.new_record.message[1]:
                message += self.new_record.message[1]

        elif change_type == 2:  # 'title_change':
            message = self.new_record.message

        elif change_type == 3:  # 'replies_num_change':
            message = self.new_record.message[0]

        elif change_type == 4:  # 'inforg_replies':
            message = self.new_record.message[0]
            if self.user.user_in_multi_folders and self.new_record.message[1]:
                message += self.new_record.message[1]
            if self.new_record.message[2]:
                message += self.new_record.message[2]

        elif change_type == 8:  # first_post_change
            message = self._compose_individual_message_on_first_post_change()
        return message

    def _compose_individual_message_on_first_post_change(self) -> str:
        """compose individual message for notification of every user on change of first post"""

        message = self.new_record.message
        region = f' ({self.region_to_show})' if self.region_to_show else ''
        message = message.format(region=region)

        return message

    def _compose_individual_message_on_new_search(self) -> str:
        """compose individual message for notification of every user on new search"""

        new_record = self.new_record
        user = self.user
        region_to_show = self.region_to_show

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
                message += (
                    f'\n<code>{COORD_FORMAT.format(float(s_lat))}, ' f'{COORD_FORMAT.format(float(s_lon))}</code>'
                )

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
        if not num_of_sent or num_of_sent in FIB_LIST:
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

            if not num_of_sent or num_of_sent in FIB_LIST:
                tip_on_click_to_copy = '<i>Совет: Координаты и телефоны можно скопировать, нажав на них.</i>'
                if not u_lat and not u_lon:
                    tip_on_home_coords = (
                        '<i>Совет: Чтобы Бот показывал Направление и Расстояние до поиска – просто '
                        'укажите ваши "Домашние координаты" в Настройках Бота.</i>'
                    )

        # TODO - yet not implemented new message template
        # obj = new_record.message_object
        # final_message = f"""{new_record.topic_emoji}Новый поиск{region_wording}!\n
        #                     {obj.activities}\n\n
        #                     {obj.clickable_name}\n\n
        #                     {place_link}\n
        #                     {clickable_coords}\n\n
        #                     {obj.managers}\n\n
        #                     {tip_on_click_to_copy}\n\n
        #                     {tip_on_home_coords}"""

        # final_message = re.sub(r'\s{3,}', '\n\n', final_message)  # clean excessive blank lines
        # final_message = re.sub(r'\s*$', '', final_message)  # clean blank symbols in the end of file
        logging.info(f'OLD - FINAL NEW MESSAGE FOR NEW SEARCH: {message}')
        # logging.info(f'NEW - FINAL NEW MESSAGE FOR NEW SEARCH: {final_message}')
        # TODO ^^^

        return message


def generate_yandex_maps_place_link2(lat: str, lon: str, param: str) -> str:
    """generate a link to yandex map with lat/lon"""

    display = 'Карта' if param == 'map' else param
    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

    return msg


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
