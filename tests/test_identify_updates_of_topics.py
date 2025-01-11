from unittest.mock import patch

import pytest

from tests.common import get_event_with_data


def test_main():
    from identify_updates_of_topics.main import main

    data = 'foo'
    with pytest.raises(ValueError):
        main(get_event_with_data(data), 'context')
    assert True


def test_get_cordinates():
    from identify_updates_of_topics.main import get_coordinates, sql_connect

    data = 'Москва, Ярославское шоссе 123'
    db = sql_connect()
    with patch('identify_updates_of_topics.main.rate_limit_for_api'):
        res = get_coordinates(db, data)
    assert (round(res[0]), round(res[1])) == (56, 38)


def test_rate_limit_for_api():
    from identify_updates_of_topics.main import rate_limit_for_api, sql_connect

    data = 'Москва, Ярославское шоссе 123'
    db = sql_connect()
    rate_limit_for_api(db, data)
    assert True


def test_get_the_list_of_ignored_folders():
    from identify_updates_of_topics.main import get_the_list_of_ignored_folders, sql_connect

    res = get_the_list_of_ignored_folders(sql_connect())
    assert not res
