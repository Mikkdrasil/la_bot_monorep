from unittest.mock import MagicMock


def test_main():
    from users_activate.main import main

    main(MagicMock(), 'context')
    assert True
