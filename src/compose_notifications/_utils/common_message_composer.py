import ast
import datetime
import logging
import re

from compose_notifications._utils.notif_common import (
    COORD_FORMAT,
    COORD_PATTERN,
    SEARCH_TOPIC_TYPES,
    ChangeType,
    LineInChangeLog,
    MessageNewTopic,
    TopicType,
    add_tel_link,
    define_dist_and_dir_to_search,
    get_coords_from_list,
)


class CommonMessageComposer:
    """
    class to compose common messages
    changes fields:
        line.message
        line.clickable_name
        line.topic_emoji
    """

    def __init__(self, line: LineInChangeLog):
        self.line = line

    def compose(self) -> None:
        self.make_com_message_texts()
        self.make_clickable_name()
        self.make_emoji()

    def make_emoji(self) -> None:
        """add specific emoji based on topic (search) type"""

        line = self.line
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

    def make_clickable_name(self) -> None:
        """add clickable name to the record"""

        line = self.line
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

    def make_com_message_texts(self) -> None:
        """add user-independent message text to the New Records"""
        line = self.line
        try:
            if line.change_type == ChangeType.topic_new:
                self._compose_com_msg_on_new_topic()
            elif line.change_type == ChangeType.topic_status_change and line.topic_type_id in SEARCH_TOPIC_TYPES:
                self._compose_com_msg_on_status_change()
            elif line.change_type == ChangeType.topic_title_change:
                self._compose_com_msg_on_title_change()
            elif line.change_type == ChangeType.topic_comment_new:
                self._compose_com_msg_on_new_comments()
            elif line.change_type == ChangeType.topic_inforg_comment_new:
                self._compose_com_msg_on_inforg_comments()
            elif line.change_type == ChangeType.topic_first_post_change:
                self._compose_com_msg_on_first_post_change()

            logging.info('New Record enriched with common Message Text')

        except Exception as e:
            logging.error('Not able to enrich New Record with common Message Texts:' + str(e))
            logging.exception(e)
            logging.info('FOR DEBUG OF ERROR – line is: ' + str(line))

    def _compose_com_msg_on_first_post_change(self) -> None:
        """compose the common, user-independent message on search first post change"""
        line = self.line

        message = line.new_value
        clickable_name = line.clickable_name
        old_lat = line.search_latitude
        old_lon = line.search_longitude
        type_id = line.topic_type_id

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
                    for deletion_line in list_of_deletions:
                        message += f'{deletion_line}\n'
                    message += '</s>'

                list_of_additions = message_dict['add']
                if list_of_additions:
                    if message:
                        message += '\n'
                    message += '➕Добавлено:\n'
                    for addition_line in list_of_additions:
                        # majority of coords in RU: lat in [30-80], long in [20-180]
                        updated_line = re.sub(COORD_PATTERN, '<code>\g<0></code>', addition_line)
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
            line.message = ''
            return

        if type_id in SEARCH_TOPIC_TYPES:
            resulting_message = (
                f'{line.topic_emoji}🔀Изменения в первом посте по {clickable_name}{region}:\n\n{message}'
                f'{coord_change_phrase}'
            )
        elif type_id == 10:
            resulting_message = (
                f'{line.topic_emoji}Изменения в описании мероприятия {clickable_name}{region}:\n\n{message}'
            )
        else:
            resulting_message = ''

        line.message = resulting_message

    def _compose_com_msg_on_inforg_comments(self) -> None:
        """compose the common, user-independent message on INFORG search comments change"""
        line = self.line

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

    def _compose_com_msg_on_new_comments(self) -> None:
        """compose the common, user-independent message on ALL search comments change"""

        line = self.line
        url_prefix = 'https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
        activity = 'мероприятию' if line.topic_type_id == TopicType.event else 'поиску'

        msg = ''
        for comment in line.comments:
            if comment.text:
                comment_text = f'{comment.text[:500]}...' if len(comment.text) > 500 else comment.text
                comment_text = add_tel_link(comment_text)
                code_pos = comment_text.find('<code>')
                text_before_code_pos = comment_text[:code_pos]
                text_from_code_pos = comment_text[code_pos:]

                msg += (
                    f' &#8226; <a href="{url_prefix}{comment.author_link}">{comment.author_nickname}</a>: '
                    f'<i>«<a href="{comment.url}">{text_before_code_pos}</a>{text_from_code_pos}»</i>\n'
                )

        msg = f'Новые комментарии по {activity} {line.clickable_name}:\n{msg}' if msg else ''

        line.message = msg, None  # TODO ???

    def _compose_com_msg_on_new_topic(self) -> None:
        """compose the common, user-independent message on new topic (search, event)"""
        line = self.line

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

    def _compose_com_msg_on_status_change(self) -> None:
        """compose the common, user-independent message on search status change"""

        line = self.line
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

    def _compose_com_msg_on_title_change(self) -> None:
        """compose the common, user-independent message on search title change"""
        line = self.line

        activity = 'мероприятия' if line.topic_type_id == TopicType.event else 'поиска'
        msg = f'{line.title} – обновление заголовка {activity} по {line.clickable_name}'

        line.message = msg
