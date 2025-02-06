import pytest

from compose_notifications._utils.commons import define_dist_and_dir_to_search, get_coords_from_list


def test_get_coords_from_list():
    messages = ['56.1234 60.5678']
    c1, c2 = get_coords_from_list(messages)
    assert c1, c2 == ('56.12340', '60.56780')


def test_define_dist_and_dir_to_search():
    dist, direction = define_dist_and_dir_to_search('56.1234', '60.56780', '55.1234', '60.56780')
    assert dist == 111.2
