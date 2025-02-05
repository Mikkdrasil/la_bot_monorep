import ast
import datetime
import logging
import re

import sqlalchemy
import sqlalchemy.connectors
import sqlalchemy.ext
import sqlalchemy.pool
from sqlalchemy.engine.base import Connection

from _dependencies.misc import age_writer, notify_admin

from .notif_common import (
    COORD_FORMAT,
    COORD_PATTERN,
    SEARCH_TOPIC_TYPES,
    WINDOW_FOR_NOTIFICATIONS_DAYS,
    ChangeType,
    Comment,
    LineInChangeLog,
    MessageNewTopic,
    TopicType,
    add_tel_link,
    define_dist_and_dir_to_search,
    get_coords_from_list,
)


class LogRecordExtractor:
    def __init__(self, conn: Connection, record_id: int | None = None) -> None:
        self.conn = conn
        self.record_id = record_id

    def get_line(self) -> LineInChangeLog | None:
        line = self.select_first_record_from_change_log(self.record_id)
        if not line:
            return None
        self.enrich_new_record(line)
        return line

    def select_first_record_from_change_log(self, record_id: int | None = None) -> LineInChangeLog | None:
        """compose the New Records list of the unique New Records in Change Log: one Record = One line in Change Log"""

        query = sqlalchemy.text(f"""
            SELECT 
                search_forum_num, changed_field, new_value, id, change_type 
            FROM change_log
            WHERE 
                (notification_sent is NULL
                OR notification_sent='s')
                
                {"AND id=:record_id" if record_id is not None else ""}

            ORDER BY id LIMIT 1; 
            """)

        query_args = {'record_id': record_id} if record_id is not None else {}
        delta_in_cl = self.conn.execute(query, **query_args).fetchall()

        if not delta_in_cl:
            logging.info('no new records found in PSQL')
            return None

        one_line_in_change_log = delta_in_cl[0]

        if not one_line_in_change_log:
            logging.info(
                f'new record is found in PSQL, however it is not list: {delta_in_cl}, {one_line_in_change_log}'
            )
            return None

        logging.info(f'new record is {one_line_in_change_log}')

        new_record = LineInChangeLog(
            forum_search_num=one_line_in_change_log[0],
            changed_field=one_line_in_change_log[1],
            new_value=one_line_in_change_log[2],
            change_log_id=one_line_in_change_log[3],
            change_type=one_line_in_change_log[4],
        )

        # TODO – there was a filtering for duplication: Inforg comments vs All Comments, but after restructuring
        #  of the scrip tech solution stopped working. The new filtering solution to be developed

        logging.info(f'New Record composed from Change Log: {str(new_record)}')

        return new_record

    def enrich_new_record(self, new_record: LineInChangeLog) -> None:
        self.delete_ended_search_following(new_record)  # issue425
        # enrich New Records List with all the updates that should be in notifications
        self.enrich_new_record_from_searches(new_record)
        self.enrich_new_record_with_search_activities(new_record)
        self.enrich_new_record_with_managers(new_record)

        self.enrich_new_record_with_comments(new_record)
        self.enrich_new_record_with_inforg_comments(new_record)

        self.enrich_new_record_with_clickable_name(new_record)
        self.enrich_new_record_with_emoji(new_record)
        self.enrich_new_record_with_com_message_texts(new_record)

    def delete_ended_search_following(self, new_record: LineInChangeLog) -> None:  # issue425
        ### Delete from user_pref_search_whitelist if the search goes to one of ending statuses

        finished_statuses = ['Завершен', 'НЖ', 'НП', 'Найден']
        if new_record.change_type == ChangeType.topic_status_change and new_record.status in finished_statuses:
            stmt = sqlalchemy.text("""DELETE FROM user_pref_search_whitelist WHERE search_id=:a;""")
            self.conn.execute(stmt, a=new_record.forum_search_num)
            logging.info(
                f'Search id={new_record.forum_search_num} with status {new_record.status} is been deleted from user_pref_search_whitelist.'
            )
        return None

    def enrich_new_record_with_emoji(self, line: LineInChangeLog) -> None:
        """add specific emoji based on topic (search) type"""

        topic_type_id = line.topic_type_id
        topic_type_dict = {
            0: '',  # search regular
            1: '🏠',  # search reverse
            2: '🚓',  # search patrol
            3: '🎓',  # search training
            4: 'ℹ️',  # search info support
            5: '🚨',  # search resonance
            10: '📝',  # event
        }
        if topic_type_id:
            line.topic_emoji = topic_type_dict[topic_type_id]
        else:
            line.topic_emoji = ''

    def enrich_new_record_with_clickable_name(self, line: LineInChangeLog) -> None:
        """add clickable name to the record"""

        if line.topic_type_id in SEARCH_TOPIC_TYPES:  # if it's search
            if line.display_name:
                line.clickable_name = f'<a href="{line.link}">{line.display_name}</a>'
            else:
                if line.name:
                    name = line.name
                else:
                    name = 'БВП'
                age_info = f' {line.age_wording}' if (name[0].isupper() and line.age) else ''
                line.clickable_name = f'<a href="{line.link}">{name}{age_info}</a>'
        else:  # if it's event or something else
            line.clickable_name = f'<a href="{line.link}">{line.title}</a>'

    def enrich_new_record_with_com_message_texts(self, line: LineInChangeLog) -> None:
        """add user-independent message text to the New Records"""

        try:
            if line.change_type == ChangeType.topic_new:
                self.compose_com_msg_on_new_topic(line)
            elif line.change_type == ChangeType.topic_status_change and line.topic_type_id in SEARCH_TOPIC_TYPES:
                self.compose_com_msg_on_status_change(line)
            elif line.change_type == ChangeType.topic_title_change:
                self.compose_com_msg_on_title_change(line)
            elif line.change_type == ChangeType.topic_comment_new:
                self.compose_com_msg_on_new_comments(line)
            elif line.change_type == ChangeType.topic_inforg_comment_new:
                self.compose_com_msg_on_inforg_comments(line)
            elif line.change_type == ChangeType.topic_first_post_change:
                self.compose_com_msg_on_first_post_change(line)

            logging.info('New Record enriched with common Message Text')

        except Exception as e:
            logging.error('Not able to enrich New Record with common Message Texts:' + str(e))
            logging.exception(e)
            logging.info('FOR DEBUG OF ERROR – line is: ' + str(line))

    def define_family_name(self, title_string: str, predefined_fam_name: str | None) -> str:
        """define family name if it's not available as A SEPARATE FIELD in Searches table"""

        # if family name is already defined
        if predefined_fam_name:
            fam_name = predefined_fam_name

        # if family name needs to be defined
        else:
            string_by_word = title_string.split()
            # exception case: when Family Name is third word
            # it happens when first two either Найден Жив or Найден Погиб with different word forms
            if string_by_word[0].lower().startswith('найд'):
                fam_name = string_by_word[2]

            # case when "Поиск приостановлен"
            elif string_by_word[1].lower().startswith('приостан'):
                fam_name = string_by_word[2]

            # case when "Поиск остановлен"
            elif string_by_word[1].lower().startswith('остановл'):
                fam_name = string_by_word[2]

            # all the other cases
            else:
                fam_name = string_by_word[1]

        return fam_name

    def enrich_new_record_from_searches(self, r_line: LineInChangeLog) -> None:
        """add the additional data from Searches into New Records"""

        try:
            sql_text = sqlalchemy.text(
                """
                WITH
                s AS (
                    SELECT search_forum_num, forum_search_title, num_of_replies, family_name, age,
                        forum_folder_id, search_start_time, display_name, age_min, age_max, status, city_locations,
                        topic_type_id
                    FROM searches
                    WHERE search_forum_num = :a
                ),
                ns AS (
                    SELECT s.search_forum_num, s.status, s.forum_search_title, s.num_of_replies, s.family_name,
                        s.age, s.forum_folder_id, sa.latitude, sa.longitude, s.search_start_time, s.display_name,
                        s.age_min, s.age_max, s.status, s.city_locations, s.topic_type_id
                    FROM s
                    LEFT JOIN search_coordinates as sa
                    ON s.search_forum_num=sa.search_id
                )
                SELECT ns.*, f.folder_display_name
                FROM ns
                LEFT JOIN geo_folders_view AS f
                ON ns.forum_folder_id = f.folder_id;
                """
            )

            s_line = self.conn.execute(sql_text, a=r_line.forum_search_num).fetchone()

            if not s_line:
                logging.info('New Record WERE NOT enriched from Searches as there was no record in searches')
                logging.info(f'New Record is {r_line}')
                logging.info(f'extract from searches is {s_line}')
                logging.exception('no search in searches table!')
                return

            r_line.status = s_line[1]
            r_line.link = f'https://lizaalert.org/forum/viewtopic.php?t={r_line.forum_search_num}'
            r_line.title = s_line[2]
            r_line.n_of_replies = s_line[3]
            r_line.name = self.define_family_name(r_line.title, s_line[4])  # cuz not all the records has names in S
            r_line.age = s_line[5]
            r_line.age_wording = age_writer(s_line[5])
            r_line.forum_folder = s_line[6]
            r_line.search_latitude = s_line[7]
            r_line.search_longitude = s_line[8]
            r_line.start_time = s_line[9]
            r_line.display_name = s_line[10]
            r_line.age_min = s_line[11]
            r_line.age_max = s_line[12]
            r_line.new_status = s_line[13]
            r_line.city_locations = s_line[14]
            r_line.topic_type_id = s_line[15]
            r_line.region = s_line[16]

            logging.info(f'TEMP – FORUM_FOLDER = {r_line.forum_folder}, while s_line = {str(s_line)}')
            logging.info(f'TEMP – CITY LOCS = {r_line.city_locations}')
            logging.info(f'TEMP – STATUS_OLD = {r_line.status}, STATUS_NEW = {r_line.new_status}')
            logging.info(f'TEMP – TOPIC_TYPE = {r_line.topic_type_id}')

            # case: when new search's status is already not "Ищем" – to be ignored
            if r_line.status != 'Ищем' and r_line.change_type in {
                ChangeType.topic_new,
                ChangeType.topic_first_post_change,
            }:
                r_line.ignore = True

            # limit notification sending only for searches started 60 days ago
            # 60 days – is a compromise and can be reviewed if community votes for another setting
            try:
                FORUM_FOLDERS_OF_SAMARA = {333, 305, 334, 306, 190}
                latest_when_alert = r_line.start_time + datetime.timedelta(days=WINDOW_FOR_NOTIFICATIONS_DAYS)
                if latest_when_alert < datetime.datetime.now() and r_line.forum_folder not in FORUM_FOLDERS_OF_SAMARA:
                    r_line.ignore = True

                    # DEBUG purposes only
                    notify_admin(
                        f'ignoring old search upd {r_line.forum_search_num} with start time {r_line.start_time}'
                    )
                # FIXME – 03.12.2023 – checking that Samara is not filtered by 60 days
                if latest_when_alert < datetime.datetime.now() and r_line.forum_folder in FORUM_FOLDERS_OF_SAMARA:
                    notify_admin(f'☀️ SAMARA >60 {r_line.link}')
                # FIXME ^^^

            except:  # noqa
                pass

            logging.info('New Record enriched from Searches')

        except Exception as e:
            logging.error('Not able to enrich New Records from Searches:')
            logging.exception(e)

    def enrich_new_record_with_search_activities(self, r_line: LineInChangeLog) -> None:
        """add the lists of current searches' activities to New Record"""

        try:
            query = sqlalchemy.text("""
                SELECT dsa.activity_name from search_activities sa
                LEFT JOIN dict_search_activities dsa ON sa.activity_type=dsa.activity_id
                WHERE
                    sa.search_forum_num = :a AND
                    sa.activity_type <> '9 - hq closed' AND
                    sa.activity_type <> '8 - info' AND
                    sa.activity_status = 'ongoing' 
                ORDER BY sa.id; 
                                                   """)

            list_of_activities = self.conn.execute(query, a=r_line.forum_search_num).fetchall()
            r_line.activities = [a_line[0] for a_line in list_of_activities]

            logging.info('New Record enriched with Search Activities')

        except Exception as e:
            logging.error('Not able to enrich New Records with Search Activities: ' + str(e))
            logging.exception(e)

    def enrich_new_record_with_managers(self, r_line: LineInChangeLog) -> None:
        """add the lists of current searches' managers to the New Record"""

        try:
            list_of_managers = self.conn.execute("""
                SELECT search_forum_num, attribute_name, attribute_value
                FROM search_attributes
                WHERE attribute_name='managers'
                ORDER BY id; 
                                                 """).fetchall()

            # look for matching Forum Search Numbers in New Records List & Search Managers
            for m_line in list_of_managers:
                # when match is found
                if r_line.forum_search_num == m_line[0] and m_line[2] != '[]':
                    r_line.managers = m_line[2]

            logging.info('New Record enriched with Managers')

        except Exception as e:
            logging.error('Not able to enrich New Records with Managers: ' + str(e))
            logging.exception(e)

    def enrich_new_record_with_comments(self, r_line: LineInChangeLog) -> None:
        """add the lists of new comments comments to the New Record"""

        # look for matching Forum Search Numbers in New Record List & Comments
        if r_line.change_type not in {ChangeType.topic_inforg_comment_new, ChangeType.topic_comment_new}:
            return

        query = sqlalchemy.text("""
                SELECT
                comment_url, comment_text, comment_author_nickname, comment_author_link,
                search_forum_num, comment_num, comment_global_num
                FROM comments 
                WHERE 
                    notification_sent IS NULL
                    AND search_forum_num = :a;
                                        """)

        try:
            comments = self.conn.execute(query, a=r_line.forum_search_num).fetchall()
            r_line.comments = self._get_comments_from_query_result(comments)
            logging.info(f'New Record enriched with Comments for all')

        except Exception as e:
            logging.error(f'Not able to enrich New Records with Comments for all:')
            logging.exception(e)

    def enrich_new_record_with_inforg_comments(self, r_line: LineInChangeLog) -> None:
        """add the lists of new inforg comments to the New Record"""

        # look for matching Forum Search Numbers in New Record List & Comments
        if r_line.change_type not in {ChangeType.topic_inforg_comment_new, ChangeType.topic_comment_new}:
            return

        query = sqlalchemy.text("""
            SELECT
            comment_url, comment_text, comment_author_nickname, comment_author_link,
            search_forum_num, comment_num, comment_global_num
            FROM comments 
            WHERE 
                notif_sent_inforg IS NULL
                AND LOWER(LEFT(comment_author_nickname,6))='инфорг'
                AND comment_author_nickname!='Инфорг кинологов'
                AND search_forum_num = :a;
                                        """)

        try:
            comments = self.conn.execute(query, a=r_line.forum_search_num).fetchall()
            r_line.comments_inforg = self._get_comments_from_query_result(comments)
            logging.info(f'New Record enriched with Comments for inforg')

        except Exception as e:
            logging.error(f'Not able to enrich New Records with Comments for inforg:')
            logging.exception(e)

    def _get_comments_from_query_result(self, query_result: list[tuple]) -> list[Comment]:
        temp_list_of_comments: list[Comment] = []

        for c_line in query_result:
            comment = Comment(
                url=c_line[0],
                text=c_line[1],
                author_nickname=c_line[2],
                author_link=c_line[3],
                search_forum_num=c_line[4],
                num=c_line[5],
            )
            # check for empty comments
            if not comment.text or comment.text.lower().startswith('резерв'):
                continue

                # some nicknames can be like >>Белый<< which crashes html markup -> we delete symbols
            comment.author_nickname = comment.author_nickname.replace('>', '')
            comment.author_nickname = comment.author_nickname.replace('<', '')

            # limitation for extra long messages
            if len(comment.text) > 3500:
                comment.text = comment.text[:2000] + '...'

            temp_list_of_comments.append(comment)

        return temp_list_of_comments

    def compose_com_msg_on_first_post_change(self, record: LineInChangeLog) -> None:
        """compose the common, user-independent message on search first post change"""

        message = record.new_value
        clickable_name = record.clickable_name
        old_lat = record.search_latitude
        old_lon = record.search_longitude
        type_id = record.topic_type_id

        region = '{region}'  # to be filled in on a stage of Individual Message preparation
        list_of_additions = None
        list_of_deletions = None

        if message and message[0] == '{':
            message_dict = ast.literal_eval(message) if message else {}

            if 'del' in message_dict.keys() and 'add' in message_dict.keys():
                message = ''
                list_of_deletions = message_dict['del']
                if list_of_deletions:
                    message += '➖Удалено:\n<s>'
                    for line in list_of_deletions:
                        message += f'{line}\n'
                    message += '</s>'

                list_of_additions = message_dict['add']
                if list_of_additions:
                    if message:
                        message += '\n'
                    message += '➕Добавлено:\n'
                    for line in list_of_additions:
                        # majority of coords in RU: lat in [30-80], long in [20-180]
                        updated_line = re.sub(COORD_PATTERN, '<code>\g<0></code>', line)
                        message += f'{updated_line}\n'
            else:
                message = message_dict['message']

        coord_change_phrase = ''
        add_lat, add_lon = get_coords_from_list(list_of_additions)
        del_lat, del_lon = get_coords_from_list(list_of_deletions)

        if old_lat and old_lon:
            old_lat = COORD_FORMAT.format(float(old_lat))
            old_lon = COORD_FORMAT.format(float(old_lon))

        if add_lat and add_lon and del_lat and del_lon and (add_lat != del_lat or add_lon != del_lon):
            distance, direction = define_dist_and_dir_to_search(del_lat, del_lon, add_lat, add_lon)
        elif add_lat and add_lon and del_lat and del_lon and (add_lat == del_lat and add_lon == del_lon):
            distance, direction = None, None
        elif add_lat and add_lon and old_lat and old_lon and (add_lat != old_lat or add_lon != old_lon):
            distance, direction = define_dist_and_dir_to_search(old_lat, old_lon, add_lat, add_lon)
        else:
            distance, direction = None, None

        if distance and direction:
            if distance >= 1:
                coord_change_phrase = f'\n\nКоординаты сместились на ~{int(distance)} км {direction}'
            else:
                coord_change_phrase = f'\n\nКоординаты сместились на ~{int(distance * 1000)} метров {direction}'

        if not message:
            record.message = ''
            return

        if type_id in SEARCH_TOPIC_TYPES:
            resulting_message = (
                f'{record.topic_emoji}🔀Изменения в первом посте по {clickable_name}{region}:\n\n{message}'
                f'{coord_change_phrase}'
            )
        elif type_id == 10:
            resulting_message = (
                f'{record.topic_emoji}Изменения в описании мероприятия {clickable_name}{region}:\n\n{message}'
            )
        else:
            resulting_message = ''

        record.message = resulting_message

    def compose_com_msg_on_inforg_comments(self, line: LineInChangeLog) -> None:
        """compose the common, user-independent message on INFORG search comments change"""

        # region_to_show = f' ({region})' if region else ''
        url_prefix = 'https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='

        msg_1, msg_2 = None, None
        msg_3 = ''
        if line.comments_inforg:
            author = None
            for comment in line.comments_inforg:
                if comment.text:
                    author = f'<a href="{url_prefix}{comment.author_link}">{comment.author_nickname}</a>'
                    msg_3 += f'<i>«<a href="{comment.url}">{comment.text}</a>»</i>\n'

            msg_3 = f':\n{msg_3}'

            msg_1 = f'{line.topic_emoji}Сообщение от {author} по {line.clickable_name}'
            if line.region:
                msg_2 = f' ({line.region})'

        line.message = msg_1, msg_2, msg_3

    def compose_com_msg_on_new_comments(self, line: LineInChangeLog) -> None:
        """compose the common, user-independent message on ALL search comments change"""

        url_prefix = 'https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
        activity = 'мероприятию' if line.topic_type_id == TopicType.event else 'поиску'

        msg = ''
        for comment in line.comments:
            if comment.text:
                comment_text = f'{comment.text[:500]}...' if len(comment.text) > 500 else comment.text
                msg += (
                    f' &#8226; <a href="{url_prefix}{comment.author_link}">{comment.author_nickname}</a>: '
                    f'<i>«<a href="{comment.url}">{comment_text}</a>»</i>\n'
                )

        msg = f'Новые комментарии по {activity} {line.clickable_name}:\n{msg}' if msg else ''

        line.message = msg, None  # TODO ???

    def compose_com_msg_on_new_topic(self, line: LineInChangeLog) -> None:
        """compose the common, user-independent message on new topic (search, event)"""

        start = line.start_time
        activities = line.activities
        managers = line.managers
        clickable_name = line.clickable_name
        topic_type_id = line.topic_type_id

        now = datetime.datetime.now()
        days_since_topic_start = (now - start).days

        # FIXME – temp limitation for only topics - cuz we don't want to filter event.
        #  Once events messaging will go smooth, this limitation to be removed.
        #  03.12.2023 – Removed to check
        # if topic_type_id in SEARCH_TOPIC_TYPES:
        # FIXME ^^^

        if days_since_topic_start >= 2:  # we do not notify users on "new" topics appeared >=2 days ago:
            line.message = [None, None, None]  # 1 - person, 2 - activities, 3 - managers
            line.message_object = None
            line.ignore = True
            return

        message = MessageNewTopic()

        if topic_type_id == TopicType.event:
            clickable_name = f'🗓️Новое мероприятие!\n{clickable_name}'
            message.clickable_name = clickable_name
            line.message = [clickable_name, None, None]
            line.message_object = message
            line.ignore = False

        # 1. List of activities – user-independent
        msg_1 = ''
        if activities:
            for act_line in activities:
                msg_1 += f'{act_line}\n'
        message.activities = msg_1

        # 2. Person
        msg_2 = clickable_name

        if clickable_name:
            message.clickable_name = clickable_name

        # 3. List of managers – user-independent
        msg_3 = ''
        if managers:
            try:
                managers_list = ast.literal_eval(managers)
                msg_3 += 'Ответственные:'
                for manager in managers_list:
                    manager_line = add_tel_link(manager)
                    msg_3 += f'\n &#8226; {manager_line}'

            except Exception as e:
                logging.error('Not able to compose New Search Message text with Managers: ' + str(e))
                logging.exception(e)

            message.managers = msg_3

        logging.info('msg 2 + msg 1 + msg 3: ' + str(msg_2) + ' // ' + str(msg_1) + ' // ' + str(msg_3))
        line.message = [msg_2, msg_1, msg_3]  # 1 - person, 2 - activities, 3 - managers
        line.message_object = message
        line.ignore = False

    def compose_com_msg_on_status_change(self, line: LineInChangeLog) -> None:
        """compose the common, user-independent message on search status change"""

        status = line.status
        region = line.region
        clickable_name = line.clickable_name

        if status == 'Ищем':
            status_info = 'Поиск возобновлён'
        elif status == 'Завершен':
            status_info = 'Поиск завершён'
        else:
            status_info = status

        msg_1 = f'{status_info} – изменение статуса по {clickable_name}'

        msg_2 = f' ({region})' if region else None

        line.message = msg_1, msg_2

    def compose_com_msg_on_title_change(self, line: LineInChangeLog) -> None:
        """compose the common, user-independent message on search title change"""

        activity = 'мероприятия' if line.topic_type_id == 10 else 'поиска'
        msg = f'{line.title} – обновление заголовка {activity} по {line.clickable_name}'

        line.message = msg
