import datetime
import logging
import re

import sqlalchemy
from sqlalchemy.engine.base import Connection

from _dependencies.commons import Topics, get_app_config, publish_to_pubsub
from _dependencies.misc import notify_admin

from .notif_common import (
    COORD_FORMAT,
    SEARCH_TOPIC_TYPES,
    ChangeType,
    LineInChangeLog,
    User,
    define_dist_and_dir_to_search,
)
from .users_list_composer import UserListFilter

CLEANER_RE = re.compile('<.*?>')

FIB_LIST = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]


class NotificationMaker:
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

            mailing_id = self.create_new_mailing_id(new_record)

            message_for_pubsub = {'triggered_by_func_id': function_id, 'text': 'initiate notifs send out'}
            publish_to_pubsub(Topics.topic_to_send_notifications, message_for_pubsub)

            for user in list_of_users:
                number_of_situations_checked += 1
                self.generate_notification_for_user(
                    new_record,
                    mailing_id,
                    user,
                )

            # mark this line as all-processed
            new_record.processed = True
            logging.info('Iterations over all Users and Updates are done')

        except Exception as e1:
            logging.info('Not able to Iterate over all Users and Updates: ')
            logging.exception(e1)

    def create_new_mailing_id(self, new_record: LineInChangeLog) -> int:
        # record into SQL table notif_mailings

        sql_text = sqlalchemy.text("""
            INSERT INTO notif_mailings (topic_id, source_script, mailing_type, change_log_id)
            VALUES (:a, :b, :c, :d)
            RETURNING mailing_id;
                        """)
        raw_data = self.conn.execute(
            sql_text,
            a=new_record.forum_search_num,
            b='notifications_script',
            c=new_record.change_type,
            d=new_record.change_log_id,
        ).fetchone()

        mail_id = raw_data[0]
        logging.info(f'mailing_id = {mail_id}')

        return mail_id

    def check_if_record_was_already_processed(self, change_log_id: int) -> bool:
        # check if this change_log record was somehow processed
        sql_text = sqlalchemy.text("""
            SELECT EXISTS (SELECT * FROM notif_mailings WHERE change_log_id=:a);
                                   """)
        record_was_processed_already = self.conn.execute(sql_text, a=change_log_id).fetchone()[0]

        # TODO: DEBUG
        if record_was_processed_already:
            logging.info('[comp_notif]: 2 MAILINGS for 1 CHANGE LOG RECORD identified')
        # TODO: DEBUG
        return record_was_processed_already

    def generate_notification_for_user(
        self,
        new_record: LineInChangeLog,
        mailing_id,
        user: User,
    ):
        change_type = new_record.change_type
        change_log_id = new_record.change_log_id

        topic_type_id = new_record.topic_type_id
        region_to_show = new_record.region if user.user_in_multi_folders else None

        this_record_was_processed_already = self.check_if_record_was_already_processed(change_log_id)

        # define if user received this message already
        if this_record_was_processed_already:
            this_user_was_notified = self.get_from_sql_if_was_notified_already(
                user.user_id, 'text', new_record.change_log_id
            )

            logging.info(f'this user was notified already {user.user_id}, {this_user_was_notified}')
            if this_user_was_notified:
                return

        # start composing individual messages (specific user on specific situation)
        user_message = MessageComposer(new_record, user, region_to_show).compose_message_for_user()
        if not user_message:
            return

        # TODO: to delete msg_group at all ?
        # messages followed by coordinates (sendMessage + sendLocation) have same group
        msg_group_id = (
            self.get_the_new_group_id()
            if change_type in {ChangeType.topic_new, ChangeType.topic_first_post_change}
            else None
        )
        # not None for new_search, field_trips_new, field_trips_change,  coord_change

        # TODO: make text more compact within 50 symbols
        message_without_html = re.sub(CLEANER_RE, '', user_message)
        message_params = {'parse_mode': 'HTML', 'disable_web_page_preview': 'True'}

        # for the new searches we add a link to web_app map
        if change_type == ChangeType.topic_new:
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

        # save to SQL the sendLocation notification for "new search"
        if change_type == ChangeType.topic_new and topic_type_id in SEARCH_TOPIC_TYPES:
            # for user tips in "new search" notifs – to increase sent messages counter
            self.stat_list_of_recipients.append(user.user_id)
            self._send_coordinates_for_new_search(new_record, mailing_id, user, change_log_id, msg_group_id)
        elif change_type == ChangeType.topic_first_post_change:
            self._send_coordinates_for_first_post_change(mailing_id, user, change_log_id, user_message, msg_group_id)

    def _send_coordinates_for_new_search(
        self, new_record: LineInChangeLog, mailing_id: int, user: User, change_log_id: int, msg_group_id: int | None
    ) -> None:
        if new_record.search_latitude and new_record.search_longitude:
            message_params = {'latitude': new_record.search_latitude, 'longitude': new_record.search_longitude}

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

    def _send_coordinates_for_first_post_change(
        self, mailing_id: int, user: User, change_log_id: int, user_message: str, msg_group_id: int | None
    ) -> None:
        try:
            list_of_coords = re.findall(r'<code>', user_message)
            if not list_of_coords or len(list_of_coords) != 1:
                return
                # that would mean that there's only 1 set of new coordinates and hence we can
                # send the dedicated sendLocation message
            both_coordinates = re.search(r'(?<=<code>).{5,100}(?=</code>)', user_message).group()
            if not both_coordinates:
                return
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
            logging.exception("Can't calculate/send coordinates")

    def get_the_new_group_id(self) -> int:
        """define the max message_group_id in notif_by_user and add +1"""

        raw_data_ = self.conn.execute("""
            SELECT MAX(message_group_id) FROM notif_by_user
            /*action='get_the_new_group_id'*/
        ;
                                      """).fetchone()

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
            if not new_record.processed:
                return
            if not new_record.ignore:
                sql_text = sqlalchemy.text("""
                    UPDATE change_log SET notification_sent = 'y' WHERE id=:a;
                                            """)
                self.conn.execute(sql_text, a=new_record.change_log_id)
                logging.info(f'The New Record {new_record.change_log_id} was marked as processed in PSQL')
            else:
                sql_text = sqlalchemy.text("""
                    UPDATE change_log SET notification_sent = 'n' WHERE id=:a;
                                            """)
                self.conn.execute(sql_text, a=new_record.change_log_id)
                logging.info(f'The New Record {new_record.change_log_id} was marked as IGNORED in PSQL')

        except Exception as e:
            # FIXME – should be a smarter way to re-process the record instead of just marking everything as processed
            # For Safety's Sake – Update Change_log SQL table, setting 'y' everywhere
            self.conn.execute("""
                UPDATE change_log SET notification_sent = 'y' WHERE notification_sent is NULL
                OR notification_sent='s';
                """)

            logging.info('Not able to mark Updates as Processed in Change Log')
            logging.exception(e)
            logging.info('Due to error, all Updates are marked as processed in Change Log')
            notify_admin('ERROR: Not able to mark Updates as Processed in Change Log!')
            # FIXME ^^^

    def mark_new_comments_as_processed(self, record: LineInChangeLog) -> None:
        """mark in SQL table Comments all the comments that were processed at this step, basing on search_forum_id"""

        try:
            # TODO – is it correct that we mark comments processes for any Comments for certain search? Looks
            #  like we can mark some comments which are not yet processed at all. Probably base on change_id? To be checked
            if record.processed and not record.ignore:
                if record.change_type == ChangeType.topic_comment_new:
                    sql_text = sqlalchemy.text("UPDATE comments SET notification_sent = 'y' WHERE search_forum_num=:a;")
                    self.conn.execute(sql_text, a=record.forum_search_num)

                elif record.change_type == ChangeType.topic_inforg_comment_new:
                    sql_text = sqlalchemy.text("UPDATE comments SET notif_sent_inforg = 'y' WHERE search_forum_num=:a;")
                    self.conn.execute(sql_text, a=record.forum_search_num)
                # FIXME ^^^

                logging.info(f'The Update {record.change_log_id} with Comments that are processed and not ignored')
                logging.info('All Comments are marked as processed')

        except Exception as e:
            # TODO – seems a vary vague solution: to mark all
            sql_text = sqlalchemy.text("""
                UPDATE comments SET notification_sent = 'y' WHERE notification_sent is Null
                OR notification_sent = 's';
                                       """)
            self.conn.execute(sql_text)
            sql_text = sqlalchemy.text("""
                UPDATE comments SET notif_sent_inforg = 'y' WHERE notif_sent_inforg is Null;
                """)
            self.conn.execute(sql_text)

            logging.info('Not able to mark Comments as Processed:')
            logging.exception(e)
            logging.info('Due to error, all Comments are marked as processed')
            notify_admin('ERROR: Not able to mark Comments as Processed!')


class MessageComposer:
    def __init__(self, new_record: LineInChangeLog, user: User, region_to_show: str | None):
        self.new_record = new_record
        self.user = user
        self.region_to_show = region_to_show

    def compose_message_for_user(self) -> str:
        change_type = self.new_record.change_type
        topic_type_id = self.new_record.topic_type_id
        if change_type == ChangeType.topic_new:
            return (
                self._compose_individual_message_on_new_search()
                if topic_type_id in SEARCH_TOPIC_TYPES
                else self.new_record.message[0]
            )

        elif change_type == ChangeType.topic_status_change and topic_type_id in SEARCH_TOPIC_TYPES:
            message = self.new_record.message[0]
            if self.user.user_in_multi_folders and self.new_record.message[1]:
                message += self.new_record.message[1]
            return message

        elif change_type == ChangeType.topic_title_change:
            return self.new_record.message  # TODO ???

        elif change_type == ChangeType.topic_comment_new:
            return self.new_record.message[0]  # TODO ???

        elif change_type == ChangeType.topic_inforg_comment_new:
            message = self.new_record.message[0]
            if self.user.user_in_multi_folders and self.new_record.message[1]:
                message += self.new_record.message[1]
            if self.new_record.message[2]:
                message += self.new_record.message[2]
            return message

        elif change_type == ChangeType.topic_first_post_change:
            return self._compose_individual_message_on_first_post_change()

        return ''

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
