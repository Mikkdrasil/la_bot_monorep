from datetime import datetime, timedelta

import pytest
from flask import Flask


def test_main():
    from api_get_active_searches.main import main

    app = Flask(__name__)

    with app.test_request_context('/', json={'app_id': 1}) as app:
        main(app.request)
    assert True


def test_evaluate_city_locations_success():
    from api_get_active_searches.main import evaluate_city_locations

    res = evaluate_city_locations('[[56.0, 64.0]]')
    assert res == [[56.0, 64.0]]


@pytest.mark.parametrize(
    'param',
    [
        [],
        [1],
        [None],
        '"foo"',
        '',
    ],
)
def test_evaluate_city_locations_fail(param):
    from api_get_active_searches.main import evaluate_city_locations

    res = evaluate_city_locations(str(param))
    assert res is None


@pytest.mark.parametrize(
    'minutes_ago,hours_ago,days_ago,result',
    [
        (0, 0, 0, ['Начинаем искать', 0]),
        (0, 1, 0, ['1 час', 0]),
        (0, 10, 0, ['10 часов', 0]),
        (0, 0, 2, ['2 дня', 2]),
    ],
)
def test_time_counter_since_search_start(minutes_ago: int, hours_ago: int, days_ago: int, result: str):
    from api_get_active_searches.main import time_counter_since_search_start

    start_datetime = datetime.now() - timedelta(minutes=minutes_ago, hours=hours_ago, days=days_ago)
    res = time_counter_since_search_start(start_datetime)
    assert res == result


def test_get_list_of_active_searches_from_db():
    from api_get_active_searches.main import get_list_of_active_searches_from_db

    data = {'depth_days': 20, 'forum_folder_id_list': [1, 2, 3]}

    res = get_list_of_active_searches_from_db(data)
    assert not res


def test_clean_up_content():
    from api_get_active_searches.main import clean_up_content

    data = '<span>some text</span>'

    res = clean_up_content(data)
    assert res == 'some text'
