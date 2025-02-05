import datetime
import logging

import sqlalchemy
import sqlalchemy.connectors
import sqlalchemy.ext
import sqlalchemy.pool
from sqlalchemy.engine.base import Connection

from _dependencies.misc import age_writer, notify_admin
from compose_notifications._utils.common_message_composer import CommonMessageComposer

from .notif_common import (
    WINDOW_FOR_NOTIFICATIONS_DAYS,
    ChangeType,
    Comment,
    LineInChangeLog,
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
        CommonMessageComposer(line).compose()
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

    def define_family_name(self, title_string: str, predefined_fam_name: str | None) -> str:
        """define family name if it's not available as A SEPARATE FIELD in Searches table
        TODO can we move it outside?
        """

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
                latest_when_alert = r_line.start_time + datetime.timedelta(days=WINDOW_FOR_NOTIFICATIONS_DAYS)
                if latest_when_alert < datetime.datetime.now():
                    FORUM_FOLDERS_OF_SAMARA = {333, 305, 334, 306, 190}
                    if r_line.forum_folder not in FORUM_FOLDERS_OF_SAMARA:
                        r_line.ignore = True

                        # DEBUG purposes only
                        notify_admin(
                            f'ignoring old search upd {r_line.forum_search_num} with start time {r_line.start_time}'
                        )
                    # FIXME – 03.12.2023 – checking that Samara is not filtered by 60 days
                    else:
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

        query = sqlalchemy.text("""
            SELECT attribute_value
            FROM search_attributes
            WHERE 
                attribute_name='managers'
                AND search_forum_num = :a;
            ORDER BY id; 
                                """)
        try:
            list_of_managers = self.conn.execute(query, a=r_line.forum_search_num).fetchall()

            # look for matching Forum Search Numbers in New Records List & Search Managers

            for m_line in list_of_managers:
                # TODO can be multiple lines with 'managers'?
                if m_line[0] != '[]':
                    r_line.managers = m_line[0]

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
