import pytest

from compose_notifications import main
from tests.common import run_smoke


def test_call_self_if_need_compose_more():
    res = run_smoke(main.call_self_if_need_compose_more)
    pass


def test_create_user_notifications_from_change_log_record():
    res = run_smoke(main.create_user_notifications_from_change_log_record)
    pass


def test_get_list_of_admins_and_testers():
    res = run_smoke(main.get_list_of_admins_and_testers)
    pass


def test_sql_connect():
    res = run_smoke(main.sql_connect)
    pass
