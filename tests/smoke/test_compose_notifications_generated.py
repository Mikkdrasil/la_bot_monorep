import pytest

import compose_notifications._utils.enrich
import compose_notifications._utils.notif_common
from compose_notifications import main
from tests.common import run_smoke


def test_add_tel_link():
    res = run_smoke(compose_notifications._utils.enrich.add_tel_link)
    pass


def test_check_if_need_compose_more():
    res = run_smoke(main.check_if_need_compose_more)
    pass


def test_compose_com_msg_on_first_post_change():
    res = run_smoke(compose_notifications._utils.notif_common.compose_com_msg_on_first_post_change)
    pass


def test_compose_com_msg_on_inforg_comments():
    res = run_smoke(compose_notifications._utils.enrich.compose_com_msg_on_inforg_comments)
    pass


def test_compose_com_msg_on_new_comments():
    res = run_smoke(compose_notifications._utils.enrich.compose_com_msg_on_new_comments)
    pass


def test_compose_com_msg_on_status_change():
    res = run_smoke(compose_notifications._utils.enrich.compose_com_msg_on_status_change)
    pass


def test_compose_com_msg_on_title_change():
    res = run_smoke(compose_notifications._utils.enrich.compose_com_msg_on_title_change)
    pass


def test_compose_individual_message_on_first_post_change():
    res = run_smoke(main.compose_individual_message_on_first_post_change)
    pass


def test_compose_individual_message_on_new_search():
    res = run_smoke(main.compose_individual_message_on_new_search)
    pass


def test_compose_new_records_from_change_log():
    res = run_smoke(main.compose_new_records_from_change_log)
    pass


def test_compose_users_list_from_users():
    res = run_smoke(main.compose_users_list_from_users)
    pass


def test_define_dist_and_dir_to_search():
    res = run_smoke(compose_notifications._utils.enrich.define_dist_and_dir_to_search)
    pass


def test_define_family_name():
    res = run_smoke(compose_notifications._utils.enrich.define_family_name)
    pass


def test_delete_ended_search_following():
    res = run_smoke(main.delete_ended_search_following)
    pass


def test_enrich_new_record_from_searches():
    res = run_smoke(compose_notifications._utils.enrich.enrich_new_record_from_searches)
    pass


def test_enrich_new_record_with_clickable_name():
    res = run_smoke(compose_notifications._utils.enrich.enrich_new_record_with_clickable_name)
    pass


def test_enrich_new_record_with_com_message_texts():
    res = run_smoke(compose_notifications._utils.enrich.enrich_new_record_with_com_message_texts)
    pass


def test_enrich_new_record_with_comments():
    res = run_smoke(compose_notifications._utils.enrich.enrich_new_record_with_comments)
    pass


def test_enrich_new_record_with_managers():
    res = run_smoke(compose_notifications._utils.enrich.enrich_new_record_with_managers)
    pass


def test_enrich_new_record_with_search_activities():
    res = run_smoke(compose_notifications._utils.enrich.enrich_new_record_with_search_activities)
    pass


def test_enrich_users_list_with_age_periods():
    res = run_smoke(compose_notifications._utils.enrich.enrich_users_list_with_age_periods)
    pass


def test_enrich_users_list_with_radius():
    res = run_smoke(compose_notifications._utils.enrich.enrich_users_list_with_radius)
    pass


def test_generate_yandex_maps_place_link2():
    res = run_smoke(main.generate_yandex_maps_place_link2)
    pass


def test_get_coords_from_list():
    res = run_smoke(compose_notifications._utils.enrich.get_coords_from_list)
    pass


def test_get_list_of_admins_and_testers():
    res = run_smoke(main.get_list_of_admins_and_testers)
    pass


def test_iterate_over_all_users():
    res = run_smoke(main.iterate_over_all_users)
    pass


def test_mark_new_comments_as_processed():
    res = run_smoke(main.mark_new_comments_as_processed)
    pass


def test_mark_new_record_as_processed():
    res = run_smoke(main.mark_new_record_as_processed)
    pass


def test_record_notification_statistics():
    res = run_smoke(main.record_notification_statistics)
    pass


def test_sql_connect():
    res = run_smoke(main.sql_connect)
    pass
