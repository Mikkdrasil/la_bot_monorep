from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# from tests.factories.db_models import ChangeLog, User
from faker import Faker
from polyfactory.factories import DataclassFactory

from compose_notifications._utils.message_composers import CommonMessageComposer
from compose_notifications._utils.notif_common import ChangeLogSavedValue, ChangeType, LineInChangeLog, TopicType

faker = Faker('ru_RU')


class LineInChageFactory(DataclassFactory[LineInChangeLog]):
    # topic_type_id = TopicType.search_regular
    # start_time = datetime.now()
    # activities = [1, 2]
    # managers = '["manager1","manager2"]'
    message = None
    clickable_name = ''
    topic_emoji = ''
    search_latitude = '56.1234'
    search_longitude = '60.1234'


def test_topic_emoji():
    record = LineInChageFactory.build(
        topic_type_id=TopicType.search_reverse,
    )
    assert not record.topic_emoji
    CommonMessageComposer(record).compose()
    assert record.topic_emoji


class TestCommonMessageComposerClickableName:
    def test_clickable_name_topic_search_with_display_name(self):
        record = LineInChageFactory.build(
            topic_type_id=TopicType.search_reverse,
        )
        assert not record.clickable_name
        CommonMessageComposer(record).compose()
        assert record.display_name in record.clickable_name

    def test_clickable_name_topic_search_without_display_name(self):
        record = LineInChageFactory.build(
            topic_type_id=TopicType.search_reverse,
            display_name='',
        )
        assert not record.clickable_name
        CommonMessageComposer(record).compose()
        assert record.name in record.clickable_name

    def test_clickable_name_topic_not_search(self):
        record = LineInChageFactory.build(
            topic_type_id=TopicType.info,
        )
        assert not record.clickable_name
        CommonMessageComposer(record).compose()
        assert record.title in record.clickable_name


class TestCommonMessageComposer:
    @pytest.mark.parametrize(
        'change_type',
        [
            change_type
            for change_type in ChangeType
            if change_type
            not in (
                ChangeType.topic_new,
                ChangeType.topic_status_change,
                ChangeType.topic_title_change,
                ChangeType.topic_comment_new,
                ChangeType.topic_inforg_comment_new,
                ChangeType.topic_first_post_change,
            )
        ],
    )
    def test_message_not_composed(self, change_type: ChangeType):
        # these change_types should not produce a message
        record = LineInChageFactory.build(
            topic_type_id=TopicType.search_reverse,
            change_type=change_type,
            message_common_part='',
        )
        CommonMessageComposer(record).compose()
        assert not record.message_common_part

    def test_topic_new(self):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_new,
            start_time=datetime.now(),
            topic_type_id=TopicType.event,
            managers='["manager1","manager2 +79001234567"]',  # TODO check phone link in separate test
            activities=['some activity'],
        )
        CommonMessageComposer(record).compose()
        assert record.message_common_part
        assert 'Новое мероприятие' in record.message_common_part[0]
        assert 'some activity' in record.message_common_part[1]
        assert 'manager2 <code>+79001234567</code>' in record.message_common_part[2]

    def test_topic_status_change(self):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_status_change,
            topic_type_id=TopicType.search_info_support,
            message_common_part='',
        )
        assert not record.message_common_part
        CommonMessageComposer(record).compose()
        assert record.message_common_part

    def test_topic_title_change(self):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_title_change,
        )
        CommonMessageComposer(record).compose()
        assert record.message_common_part

    def test_topic_comment_new(self):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_comment_new,
        )
        CommonMessageComposer(record).compose()
        assert record.message_common_part

    def test_topic_inforg_comment_new(self):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_inforg_comment_new,
        )
        CommonMessageComposer(record).compose()
        assert record.message_common_part

    def test_topic_first_post_change_1(self):
        new_value = r"{'del': ['Иван (Иванов)'], 'add': [], 'message': 'Удалено:\n<s>Иван (Иванов)\n</s>'}"
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
        )
        CommonMessageComposer(record).compose()
        assert (
            record.message_common_part
            == '🔀Изменения в первом посте по {region}:\n\n➖Удалено:\n<s>Иван (Иванов)\n</s>'
        )

    def test_topic_first_post_change_2(self):
        new_value = r"{'del': [], 'add': ['Иван (Иванов)'], 'message': 'Добавлено:\n<s>Иван (Иванов)\n</s>'}"
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
        )
        CommonMessageComposer(record).compose()
        assert record.message_common_part == '🔀Изменения в первом посте по {region}:\n\n➕Добавлено:\nИван (Иванов)\n'

    def test_topic_first_post_change_3(self):
        new_value = 'Удалена информация:\
<s>Координаты пропажи: 53.534658, 49.324723\
</s>'

        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
        )
        CommonMessageComposer(record).compose()
        assert (
            record.message_common_part
            == '🔀Изменения в первом посте по {region}:\n\nУдалена информация:<s>Координаты пропажи: 53.534658, 49.324723</s>'
        )

    def test_topic_first_post_change_4(self):
        new_value = '➖Удалено:\
<s>Ожидается выезд!\
</s>\
➕Добавлено:\
Штаб начнёт работать с 14:00 по адресу:\
Стоянка на заправке Газпромнефть, Маньковский разворот, Сергиево-Посадский г.о.\
56.376108, 38.108829\
'

        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
            search_latitude='56.1234',
            search_longitude='60.1234',
        )
        CommonMessageComposer(record).compose()
        assert (
            record.message_common_part
            == '🔀Изменения в первом посте по {region}:\n\n➖Удалено:<s>Ожидается выезд!</s>➕Добавлено:Штаб начнёт работать с 14:00 по адресу:Стоянка на заправке Газпромнефть, Маньковский разворот, Сергиево-Посадский г.о.56.376108, 38.108829'
        )

    def test_topic_first_post_change_5(self):
        new_value = r"{'del': [], 'add': ['Новые координаты 57.1234 61.12345']}"
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
        )
        CommonMessageComposer(record).compose()
        assert (
            record.message_common_part
            == '🔀Изменения в первом посте по {region}:\n\n➕Добавлено:\nНовые координаты <code>57.1234 61.12345</code>\n\n\nКоординаты сместились на ~126 км &#8601;&#xFE0E;'
        )


def test_parse_change_log_saved_value_dict():
    saved_value = r"{'del': [], 'add': ['Новые координаты 57.1234 61.12345']}"

    res = ChangeLogSavedValue.from_db_saved_value(saved_value)
    assert res.additions
    assert not res.deletions
    assert res.message == ''


def test_parse_change_log_saved_value_str():
    saved_value = r'Внимание! Изменения.'

    res = ChangeLogSavedValue.from_db_saved_value(saved_value)
    assert not res.additions
    assert not res.deletions
    assert res.message == 'Внимание! Изменения.'


def test_parse_change_log_saved_value_dict_with_extra_fields():
    """should be parsed too"""
    saved_value = r"{'del': ['a'], 'add': [], 'foo': 1}"

    res = ChangeLogSavedValue.from_db_saved_value(saved_value)
    assert res.deletions
