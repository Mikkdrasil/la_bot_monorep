import pytest

from compose_notifications._utils.notif_common import get_coords_from_list


def test_get_coords_from_list():
    messages = ['56.1234 60.5678']
    c1, c2 = get_coords_from_list(messages)
    assert c1, c2 == ('56.12340', '60.56780')
