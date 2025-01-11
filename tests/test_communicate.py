from unittest.mock import MagicMock


def test_update_and_download_list_of_regions():
    from communicate.main import main

    main(MagicMock())
