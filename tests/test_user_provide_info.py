from unittest.mock import MagicMock


def test_main():
    from user_provide_info.main import main

    main(MagicMock())
    assert True
