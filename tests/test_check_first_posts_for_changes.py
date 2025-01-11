from unittest.mock import MagicMock


def test_main():
    from check_first_posts_for_changes.main import main

    main(MagicMock(), 'context')
    assert True
