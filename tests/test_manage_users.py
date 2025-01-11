from unittest.mock import MagicMock


def test_main():
    from manage_users.main import main

    main(MagicMock(), 'context')
    assert True
