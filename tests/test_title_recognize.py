from flask import Flask


def test_main_positive():
    from title_recognize.main import main

    app = Flask(__name__)

    with app.test_request_context('/', json={'title': 'Пропал человек'}) as app:
        request = app.request
        res = main(request)

    assert 'fail' not in res


def test_main_wrong_request():
    from title_recognize.main import main

    app = Flask(__name__)

    with app.test_request_context('/', json={'foo': 'bar'}) as app:
        request = app.request
        res = main(request)

    assert 'fail' in res


def test_recognize_title():
    from title_recognize.main import recognize_title

    title = 'Пропал мужчина. ФИО - Иванов Иван Иванович. Возраст 37 лет. Ярославская область.'
    res = recognize_title(title, 'status_only')
    assert res == {
        'topic_type': 'search',
        'status': 'Ищем',
        'persons': {
            'total_persons': 1,
            'total_name': 'мужчина',
            'total_display_name': 'Мужчина 37 лет',
            'age_min': 37,
            'age_max': 37,
            'person': [
                {
                    'name': 'мужчина',
                    'age': 37,
                    'display_name': 'Мужчина 37 лет',
                    'number_of_persons': 1,
                }
            ],
        },
    }
