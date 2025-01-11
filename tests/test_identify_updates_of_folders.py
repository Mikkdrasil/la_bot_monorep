from unittest.mock import MagicMock, patch

import pytest
from google.cloud import storage

from tests.common import get_event_with_data


def test_main():
    from identify_updates_of_folders.main import main

    data = 'a = 1'
    event = get_event_with_data(data)
    with patch.object(storage.Client, '__init__', MagicMock(return_value=None)):
        with pytest.raises(SyntaxError):
            main(event, 'context')
        assert True
