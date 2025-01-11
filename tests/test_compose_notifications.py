from unittest.mock import MagicMock


def test_main():
    from compose_notifications.main import main

    main(MagicMock(), 'context')
    assert True
