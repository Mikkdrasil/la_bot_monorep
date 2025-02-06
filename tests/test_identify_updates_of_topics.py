from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from _dependencies.commons import sqlalchemy_get_pool
from identify_updates_of_topics import main
from tests.common import get_event_with_data
from title_recognize.main import recognize_title


@pytest.fixture
def db():
    return sqlalchemy_get_pool(10, 10)


@pytest.fixture(autouse=True)
def patch_google_cloud_storage():
    with patch('google.cloud.storage.Client'):
        yield


@pytest.fixture(autouse=True)
def common_patches():
    def fake_api_call(function: str, data: dict):
        reco_data = recognize_title(data['title'], None)
        return {'status': 'ok', 'recognition': reco_data}

    with (
        patch.object(main, 'requests_session', requests.Session()),
        patch.object(main, 'make_api_call', fake_api_call),
        # patch.object(main, 'parse_search_profile', Mock(return_value='foo')),
        patch('compose_notifications.main.call_self_if_need_compose_more'),  # avoid recursion in tests
    ):
        yield


@pytest.fixture()
def mock_http_get():
    with (
        patch.object(main.requests_session, 'get') as mock_http,
    ):
        yield mock_http


def test_main():
    data = 'foo'
    with pytest.raises(ValueError):
        main.main(get_event_with_data(data), 'context')
    assert True


def test_get_cordinates(db):
    data = 'Москва, Ярославское шоссе 123'
    with patch('identify_updates_of_topics.main.rate_limit_for_api'):
        res = main.get_coordinates(db, data)
    assert res == (None, None)


def test_rate_limit_for_api(db):
    data = 'Москва, Ярославское шоссе 123'

    main.rate_limit_for_api(db, data)


def test_get_the_list_of_ignored_folders():
    res = main.get_the_list_of_ignored_folders(main.sql_connect())
    assert not res


def test_parse_one_folder(db, mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

    forum_search_folder_id = 276
    summaries, details = main.parse_one_folder(db, forum_search_folder_id)
    assert summaries == [
        ['Жив Иванов Иван, 10 лет, ЗАО, г. Москва', 29],
        ['Пропал Петров Петр Петрович, 48 лет, ЗелАО, г. Москва - Тверская обл.', 116],
    ]
    assert len(details) == 2


def test_process_one_folder(db, mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

    forum_search_folder_id = 276
    with patch.object(main, 'parse_search_profile', Mock(return_value='foo')):
        update_trigger, changed_ids = main.process_one_folder(db, forum_search_folder_id)
    assert update_trigger is True


def test_main_full_scenario(mock_http_get):
    # NO SMOKE TEST identify_updates_of_topics.main.main

    mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

    forum_search_folder_id = 276
    data = [(forum_search_folder_id,)]
    with patch.object(main, 'parse_search_profile', Mock(return_value='foo')):
        main.main(get_event_with_data(str(data)), 'context')


def test_set_cloud_storage():
    # NO SMOKE TEST identify_updates_of_topics.main.set_cloud_storage
    main.set_cloud_storage('name', 1)


def test_write_snapshot_to_cloud_storage():
    # NO SMOKE TEST identify_updates_of_topics.main.write_snapshot_to_cloud_storage
    main.write_snapshot_to_cloud_storage('name', b'some', 1)


def test_parse_one_comment(db, mock_http_get):
    # NO SMOKE TEST identify_updates_of_topics.main.parse_one_comment
    mock_http_get.return_value.content = Path('tests/fixtures/forum_comment.html').read_bytes()

    there_are_inforg_comments = main.parse_one_comment(db, 1, 1)
    assert there_are_inforg_comments


def test_parse_search_profile(db, mock_http_get):
    # NO SMOKE TEST identify_updates_of_topics.main.parse_search_profile
    mock_http_get.return_value.content = Path('tests/fixtures/forum_comment.html').read_bytes()
    res = main.parse_search_profile(1)
    assert res


def test_update_change_log_and_searches(db):
    # NO SMOKE TEST identify_updates_of_topics.main.update_change_log_and_searches
    res = main.update_change_log_and_searches(db, 1)
    pass


def test_visibility_check():
    # NO SMOKE TEST identify_updates_of_topics.main.visibility_check
    response = Mock()
    response.content = b'foo'
    page_is_visible = main.visibility_check(response, 1)
    assert page_is_visible
