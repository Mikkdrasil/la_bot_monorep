from unittest.mock import MagicMock


def test_main():
    from archive_notifications.main import main

    main(MagicMock(), 'context')
    assert True
