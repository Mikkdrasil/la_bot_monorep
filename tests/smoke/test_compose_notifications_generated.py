import pytest

import compose_notifications._utils.notifications_maker
import compose_notifications._utils.users_list_composer
from compose_notifications import main
from tests.common import run_smoke


def test_check_if_age_requirements_met():
    res = run_smoke(compose_notifications._utils.notifications_maker.check_if_age_requirements_met)
    pass


def test_check_if_need_compose_more():
    res = run_smoke(main.call_self_if_need_compose_more)
    pass


def test_compose_individual_message_on_first_post_change():
    res = run_smoke(compose_notifications._utils.notifications_maker.compose_individual_message_on_first_post_change)
    pass


def test_compose_individual_message_on_new_search():
    res = run_smoke(compose_notifications._utils.notifications_maker.compose_individual_message_on_new_search)
    pass


def test_compose_new_records_from_change_log():
    res = run_smoke(main.select_first_record_from_change_log)
    pass


def test_crop_user_list():
    res = run_smoke(compose_notifications._utils.notifications_maker.crop_user_list)
    pass


def test_generate_yandex_maps_place_link2():
    res = run_smoke(compose_notifications._utils.notifications_maker.generate_yandex_maps_place_link2)
    pass


def test_get_from_sql_if_was_notified_already():
    res = run_smoke(compose_notifications._utils.notifications_maker.get_from_sql_if_was_notified_already)
    pass


def test_get_from_sql_list_of_users_with_prepared_message():
    res = run_smoke(compose_notifications._utils.notifications_maker.get_from_sql_list_of_users_with_prepared_message)
    pass


def test_get_list_of_admins_and_testers():
    res = run_smoke(main.get_list_of_admins_and_testers)
    pass


def test_get_the_new_group_id():
    res = run_smoke(compose_notifications._utils.notifications_maker.get_the_new_group_id)
    pass


def test_iterate_over_all_users():
    res = run_smoke(compose_notifications._utils.notifications_maker.generate_notifications_for_users)
    pass


def test_iterate_users_generate_one_notification():
    res = run_smoke(compose_notifications._utils.notifications_maker.generate_notification_for_user)
    pass


def test_mark_new_comments_as_processed():
    res = run_smoke(compose_notifications._utils.notifications_maker.mark_new_comments_as_processed)
    pass


def test_mark_new_record_as_processed():
    res = run_smoke(compose_notifications._utils.notifications_maker.mark_new_record_as_processed)
    pass


def test_process_mailing_id():
    res = run_smoke(compose_notifications._utils.notifications_maker.process_mailing_id)
    pass


def test_process_new_record():
    res = run_smoke(main.create_user_notifications_from_change_log_record)
    pass


def test_record_notification_statistics():
    res = run_smoke(compose_notifications._utils.notifications_maker.record_notification_statistics)
    pass


def test_save_to_sql_notif_by_user():
    res = run_smoke(compose_notifications._utils.notifications_maker.save_to_sql_notif_by_user)
    pass


def test_sql_connect():
    res = run_smoke(main.sql_connect)
    pass
