from unittest.mock import MagicMock, patch


def test_main():
    from send_notifications.main import main

    with (
        patch('send_notifications.main.SCRIPT_SOFT_TIMEOUT_SECONDS', 1),
        patch('send_notifications.main.analytics_parsed_times', [1]),
    ):
        main(MagicMock(), 'context')
    assert True
