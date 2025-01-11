import pytest

from tests.common import get_event_with_data


def test_main():
    from identify_updates_of_first_posts.main import main

    with pytest.raises(ValueError):
        main(get_event_with_data('foo'), 'context')
    assert True
