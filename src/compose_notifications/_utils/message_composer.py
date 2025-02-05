import ast
import datetime
import logging
import re

from .notif_common import (
    COORD_FORMAT,
    COORD_PATTERN,
    SEARCH_TOPIC_TYPES,
    ChangeLogSavedValue,
    ChangeType,
    LineInChangeLog,
    TopicType,
    User,
    add_tel_link,
    define_dist_and_dir_to_search,
    get_coords_from_list,
)

FIB_LIST = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]


class MessageComposer:
    def __init__(self, new_record: LineInChangeLog):
        self.new_record = new_record

    def compose_message_for_user(self, user: User) -> str:
        change_type = self.new_record.change_type
        topic_type_id = self.new_record.topic_type_id

        if change_type == ChangeType.topic_new:
            common_message_parts = self._compose_com_msg_on_new_topic()
            if topic_type_id in SEARCH_TOPIC_TYPES:
                return self._compose_individual_message_on_new_search(user, common_message_parts)
            else:
                return common_message_parts[0]

        elif change_type == ChangeType.topic_status_change and topic_type_id in SEARCH_TOPIC_TYPES:
            return self._compose_msg_on_status_change(user)

        elif change_type == ChangeType.topic_title_change:
            return self._compose_com_msg_on_title_change()

        elif change_type == ChangeType.topic_comment_new:
            return self._compose_com_msg_on_new_comments()

        elif change_type == ChangeType.topic_inforg_comment_new:
            return self._compose_com_msg_on_inforg_comments(user)

        elif change_type == ChangeType.topic_first_post_change:
            common_message = self._compose_com_msg_on_first_post_change()
            return self._compose_individual_message_on_first_post_change(user, common_message)

        return ''

    def _compose_individual_message_on_first_post_change(self, user: User, common_message: str) -> str:
        """compose individual message for notification of every user on change of first post"""
        region_to_show = self.new_record.region if user.user_in_multi_folders else None
        region = f' ({region_to_show})' if region_to_show else ''
        message = common_message.format(region=region)

        return message

    def _compose_individual_message_on_new_search(self, user: User, common_message_parts: tuple[str, str, str]) -> str:
        """compose individual message for notification of every user on new search"""

        new_record = self.new_record
        region_to_show = self.new_record.region if user.user_in_multi_folders else None

        s_lat = new_record.search_latitude
        s_lon = new_record.search_longitude
        u_lat = user.user_latitude
        u_lon = user.user_longitude
        num_of_sent = user.user_new_search_notifs

        region_wording = f' в регионе {region_to_show}' if region_to_show else ''

        # 0. Heading and Region clause if user is 'multi-regional'
        message = f'{new_record.topic_emoji}Новый поиск{region_wording}!\n'

        # 1. Search important attributes - common part (e.g. 'Внимание, выезд!)
        if common_message_parts[1]:
            message += common_message_parts[1]

        # 2. Person (e.g. 'Иванов 60' )
        message += '\n' + common_message_parts[0]

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
        if common_message_parts[2]:
            message += '\n\n' + common_message_parts[2]

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
        logging.info(f'OLD - FINAL NEW MESSAGE FOR NEW SEARCH: {message}')

        return message

    def _compose_msg_on_status_change(self, user: User) -> str:
        """compose the common, user-independent message on search status change"""

        line = self.new_record

        if line.status == 'Ищем':
            status_info = 'Поиск возобновлён'
        elif line.status == 'Завершен':
            status_info = 'Поиск завершён'
        else:
            status_info = line.status

        message = f'{status_info} – изменение статуса по {line.clickable_name}'

        if user.user_in_multi_folders and line.region:
            message += f' ({line.region})'

        return message

    def _compose_com_msg_on_title_change(self) -> str:
        """compose the common, user-independent message on search title change"""
        line = self.new_record

        activity = 'мероприятия' if line.topic_type_id == TopicType.event else 'поиска'
        msg = f'{line.title} – обновление заголовка {activity} по {line.clickable_name}'

        return msg

    def _compose_com_msg_on_new_comments(self) -> str:
        """compose the common, user-independent message on ALL search comments change"""

        line = self.new_record
        url_prefix = 'https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
        activity = 'мероприятию' if line.topic_type_id == TopicType.event else 'поиску'

        msg = ''
        for comment in line.comments:
            if comment.text:
                comment_text = f'{comment.text[:500]}...' if len(comment.text) > 500 else comment.text
                comment_text = add_tel_link(comment_text)
                code_pos = comment_text.find('<code>')
                if code_pos != -1:
                    text_before_code_pos = comment_text[:code_pos]
                    text_from_code_pos = comment_text[code_pos:]
                else:
                    text_before_code_pos = comment_text
                    text_from_code_pos = ''

                msg += (
                    f' &#8226; <a href="{url_prefix}{comment.author_link}">{comment.author_nickname}</a>: '
                    f'<i>«<a href="{comment.url}">{text_before_code_pos}</a>{text_from_code_pos}»</i>\n'
                )

        msg = f'Новые комментарии по {activity} {line.clickable_name}:\n{msg}' if msg else ''

        return msg

    def _compose_com_msg_on_inforg_comments(self, user: User) -> str:
        """compose the message on INFORG search comments change"""
        line = self.new_record
        if not line.comments_inforg:
            return ''

        url_prefix = 'https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='

        title_str, region_str, comment_str, author = '', '', '', ''
        for comment in line.comments_inforg:
            if comment.text:
                author = f'<a href="{url_prefix}{comment.author_link}">{comment.author_nickname}</a>'
                comment_str += f'<i>«<a href="{comment.url}">{comment.text}</a>»</i>\n'

        comment_str = f':\n{comment_str}'

        title_str = f'{line.topic_emoji}Сообщение от {author} по {line.clickable_name}'
        if line.region:
            region_str = f' ({line.region})'

        message = title_str
        if user.user_in_multi_folders and region_str:
            message += region_str
        if comment_str:
            message += comment_str

        return message

    def _compose_com_msg_on_first_post_change(self) -> str:
        """compose the common, user-independent message on search first post change"""
        line = self.new_record

        region = '{region}'  # to be filled in on a stage of Individual Message preparation

        saved_message = ChangeLogSavedValue.from_db_saved_value(line.new_value)

        if saved_message.deletions or saved_message.additions:
            message = ''
            if saved_message.deletions:
                message += '➖Удалено:\n<s>'
                for deletion_line in saved_message.deletions:
                    message += f'{deletion_line}\n'
                message += '</s>'

            if saved_message.additions:
                if message:
                    message += '\n'
                message += '➕Добавлено:\n'
                for addition_line in saved_message.additions:
                    # majority of coords in RU: lat in [30-80], long in [20-180]
                    updated_line = re.sub(COORD_PATTERN, '<code>\g<0></code>', addition_line)
                    message += f'{updated_line}\n'
        else:
            message = saved_message.message

        if not message:
            return ''

        clickable_name = line.clickable_name
        if line.topic_type_id in SEARCH_TOPIC_TYPES:
            coord_change_phrase = self._get_coord_change_phrase(
                line.search_latitude,
                line.search_longitude,
                saved_message.additions,
                saved_message.deletions,
            )
            resulting_message = (
                f'{line.topic_emoji}🔀Изменения в первом посте по {clickable_name}{region}:\n\n{message}'
                f'{coord_change_phrase}'
            )
        elif line.topic_type_id == TopicType.event:
            resulting_message = (
                f'{line.topic_emoji}Изменения в описании мероприятия {clickable_name}{region}:\n\n{message}'
            )
        else:
            resulting_message = ''

        return resulting_message

    def _compose_com_msg_on_new_topic(self) -> tuple[str, str, str]:
        """compose the common, user-independent message on new topic (search, event)"""

        line = self.new_record

        managers = line.managers
        clickable_name = line.clickable_name
        topic_type_id = line.topic_type_id

        if topic_type_id == TopicType.event:
            clickable_name = f'🗓️Новое мероприятие!\n{clickable_name}'

        activities_str = ''
        for act_line in line.activities:
            activities_str += f'{act_line}\n'

        person_str = clickable_name

        managers_str = ''
        if managers:
            try:
                managers_list = ast.literal_eval(managers)
                managers_str += 'Ответственные:'
                for manager in managers_list:
                    manager_line = add_tel_link(manager)
                    managers_str += f'\n &#8226; {manager_line}'

            except Exception as e:
                logging.error('Not able to compose New Search Message text with Managers: ' + str(e))
                logging.exception(e)

        logging.info(
            'msg 2 + msg 1 + msg 3: ' + str(person_str) + ' // ' + str(activities_str) + ' // ' + str(managers_str)
        )
        return person_str, activities_str, managers_str  # 1 - person, 2 - activities, 3 - managers

    def _get_coord_change_phrase(
        self,
        old_lat: str | None,
        old_lon: str | None,
        list_of_additions: list[str],
        list_of_deletions: list[str],
    ) -> str:
        coord_change_phrase = ''
        add_lat, add_lon = get_coords_from_list(list_of_additions)
        del_lat, del_lon = get_coords_from_list(list_of_deletions)

        if old_lat and old_lon:
            old_lat = COORD_FORMAT.format(float(old_lat))
            old_lon = COORD_FORMAT.format(float(old_lon))

        if add_lat and add_lon and del_lat and del_lon:
            if add_lat != del_lat or add_lon != del_lon:
                distance, direction = define_dist_and_dir_to_search(del_lat, del_lon, add_lat, add_lon)
            elif add_lat == del_lat and add_lon == del_lon:
                # no change in coordinates
                return ''
        elif add_lat and add_lon and old_lat and old_lon and (add_lat != old_lat or add_lon != old_lon):
            distance, direction = define_dist_and_dir_to_search(old_lat, old_lon, add_lat, add_lon)
        else:
            return ''

        if distance and direction:
            if distance >= 1:
                coord_change_phrase = f'\n\nКоординаты сместились на ~{int(distance)} км {direction}'
            else:
                coord_change_phrase = f'\n\nКоординаты сместились на ~{int(distance * 1000)} метров {direction}'

        return coord_change_phrase


def generate_yandex_maps_place_link2(lat: str, lon: str, param: str) -> str:
    """generate a link to yandex map with lat/lon"""

    display = 'Карта' if param == 'map' else param
    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

    return msg
