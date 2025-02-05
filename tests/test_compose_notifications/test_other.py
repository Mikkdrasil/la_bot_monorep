import pytest

from compose_notifications._utils.notif_common import get_coords_from_list
from compose_notifications._utils.notifications_maker import check_if_age_requirements_met


@pytest.mark.parametrize(
    'search_ages, user_ages, equals',
    [
        ([1, 2], [(1, 2)], True),
        ([1, 3], [(1, 2)], True),
        ([1, 2], [(2, 3)], True),
        ([3, 4], [(1, 2)], False),
        ([1, 2], [(3, 4)], False),
        ([3, 4], [(1, 2), (2, 3)], True),
        ([3, 4], [(1, 2), (5, 6)], False),
        ([], [], True),
        ([None, None], [], True),
    ],
)
def test_age_requirements_check(search_ages, user_ages, equals):
    assert check_if_age_requirements_met(search_ages, user_ages) == equals


def test_define_dist_and_dir_to_search():
    from compose_notifications._utils.notifications_maker import define_dist_and_dir_to_search

    dist, direction = define_dist_and_dir_to_search('56.1234', '60.56780', '55.1234', '60.56780')
    assert dist == 111.2


def test_get_coords_from_list():
    messages = ['56.1234 60.5678']
    c1, c2 = get_coords_from_list(messages)
    assert c1, c2 == ('56.12340', '60.56780')
