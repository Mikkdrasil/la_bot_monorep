from unittest.mock import MagicMock


def test_main():
    from send_notifications_helper_2.main import main

    main(MagicMock(), 'context')
    assert True
