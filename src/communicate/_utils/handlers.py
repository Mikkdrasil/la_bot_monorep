from telegram import ReplyKeyboardMarkup

from .buttons import MainSettingsMenu, NotificationSettingsMenu, b_act_titles, b_back_to_start
from .database import compose_user_preferences_message, save_preference


def handle_notification_preferences(cur, got_message, user_id):
    if got_message == NotificationSettingsMenu.b_act_all:
        bot_message = (
            'Супер! теперь вы будете получать уведомления в телеграм в случаях: '
            'появление нового поиска, изменение статуса поиска (стоп, НЖ, НП), '
            'появление новых комментариев по всем поискам. Вы в любой момент '
            'можете изменить список уведомлений'
        )
        save_preference(cur, user_id, 'all')

        # save preference for -ALL
    elif got_message == NotificationSettingsMenu.b_deact_all:
        bot_message = 'Вы можете настроить типы получаемых уведомлений более гибко'
        save_preference(cur, user_id, '-all')

        # save preference for +NEW SEARCHES
    elif got_message == NotificationSettingsMenu.b_act_new_search:
        bot_message = (
            'Отлично! Теперь вы будете получать уведомления в телеграм при '
            'появлении нового поиска. Вы в любой момент можете изменить '
            'список уведомлений'
        )
        save_preference(cur, user_id, 'new_searches')

        # save preference for -NEW SEARCHES
    elif got_message == NotificationSettingsMenu.b_deact_new_search:
        bot_message = 'Записали'
        save_preference(cur, user_id, '-new_searches')

        # save preference for +STATUS UPDATES
    elif got_message == NotificationSettingsMenu.b_act_stat_change:
        bot_message = (
            'Отлично! теперь вы будете получать уведомления в телеграм при '
            'изменении статуса поисков (НЖ, НП, СТОП и т.п.). Вы в любой момент '
            'можете изменить список уведомлений'
        )
        save_preference(cur, user_id, 'status_changes')

        # save preference for -STATUS UPDATES
    elif got_message == NotificationSettingsMenu.b_deact_stat_change:
        bot_message = 'Записали'
        save_preference(cur, user_id, '-status_changes')

        # save preference for TITLE UPDATES
    elif got_message == b_act_titles:
        bot_message = 'Отлично!'
        save_preference(cur, user_id, 'title_changes')

        # save preference for +COMMENTS
    elif got_message == NotificationSettingsMenu.b_act_all_comments:
        bot_message = (
            'Отлично! Теперь все новые комментарии будут у вас! Вы в любой момент ' 'можете изменить список уведомлений'
        )
        save_preference(cur, user_id, 'comments_changes')

        # save preference for -COMMENTS
    elif got_message == NotificationSettingsMenu.b_deact_all_comments:
        bot_message = (
            'Записали. Мы только оставили вам включенными уведомления о '
            'комментариях Инфорга. Их тоже можно отключить'
        )
        save_preference(cur, user_id, '-comments_changes')

        # save preference for +InforgComments
    elif got_message == NotificationSettingsMenu.b_act_inforg_com:
        bot_message = (
            'Если вы не подписаны на уведомления по всем комментариям, то теперь '
            'вы будете получать уведомления о комментариях от Инфорга. Если же вы '
            'уже подписаны на все комментарии – то всё остаётся без изменений: бот '
            'уведомит вас по всем комментариям, включая от Инфорга'
        )
        save_preference(cur, user_id, 'inforg_comments')

        # save preference for -InforgComments
    elif got_message == NotificationSettingsMenu.b_deact_inforg_com:
        bot_message = 'Вы отписались от уведомлений по новым комментариям от Инфорга'
        save_preference(cur, user_id, '-inforg_comments')

        # save preference for +FieldTripsNew
    elif got_message == NotificationSettingsMenu.b_act_field_trips_new:
        bot_message = (
            'Теперь вы будете получать уведомления о новых выездах по уже идущим '
            'поискам. Обратите внимание, что это не рассылка по новым темам на '
            'форуме, а именно о том, что в существующей теме в ПЕРВОМ посте '
            'появилась информация о новом выезде'
        )
        save_preference(cur, user_id, 'field_trips_new')

        # save preference for -FieldTripsNew
    elif got_message == NotificationSettingsMenu.b_deact_field_trips_new:
        bot_message = 'Вы отписались от уведомлений по новым выездам'
        save_preference(cur, user_id, '-field_trips_new')

        # save preference for +FieldTripsChange
    elif got_message == NotificationSettingsMenu.b_act_field_trips_change:
        bot_message = (
            'Теперь вы будете получать уведомления о ключевых изменениях при '
            'выездах, в т.ч. изменение или завершение выезда. Обратите внимание, '
            'что эта рассылка отражает изменения только в ПЕРВОМ посте поиска.'
        )
        save_preference(cur, user_id, 'field_trips_change')

        # save preference for -FieldTripsChange
    elif got_message == NotificationSettingsMenu.b_deact_field_trips_change:
        bot_message = 'Вы отписались от уведомлений по изменениям выездов'
        save_preference(cur, user_id, '-field_trips_change')

        # save preference for +CoordsChange
    elif got_message == NotificationSettingsMenu.b_act_coords_change:
        bot_message = (
            'Если у штаба поменяются координаты (и об этом будет написано в первом '
            'посте на форуме) – бот уведомит вас об этом'
        )
        save_preference(cur, user_id, 'coords_change')

        # save preference for -CoordsChange
    elif got_message == NotificationSettingsMenu.b_deact_coords_change:
        bot_message = 'Вы отписались от уведомлений о смене места (координат) штаба'
        save_preference(cur, user_id, '-coords_change')

        # save preference for -FirstPostChanges
    elif got_message == NotificationSettingsMenu.b_act_first_post_change:
        bot_message = (
            'Теперь вы будете получать уведомления о важных изменениях в Первом Посте'
            ' Инфорга, где обозначено описание каждого поиска'
        )
        save_preference(cur, user_id, 'first_post_changes')

        # save preference for -FirstPostChanges
    elif got_message == NotificationSettingsMenu.b_deact_first_post_change:
        bot_message = (
            'Вы отписались от уведомлений о важных изменениях в Первом Посте' ' Инфорга c описанием каждого поиска'
        )
        save_preference(cur, user_id, '-first_post_changes')

        # GET what are preferences
    elif got_message == MainSettingsMenu.b_set_pref_notif_type:
        prefs = compose_user_preferences_message(cur, user_id)
        if prefs[0] == 'пока нет включенных уведомлений' or prefs[0] == 'неизвестная настройка':
            bot_message = 'Выберите, какие уведомления вы бы хотели получать'
        else:
            bot_message = 'Сейчас у вас включены следующие виды уведомлений:\n'
            bot_message += prefs[0]

    else:
        bot_message = 'empty message'

    if got_message == NotificationSettingsMenu.b_act_all:
        keyboard_notifications_flexible = [[NotificationSettingsMenu.b_deact_all], [b_back_to_start]]
    elif got_message == NotificationSettingsMenu.b_deact_all:
        keyboard_notifications_flexible = [
            [NotificationSettingsMenu.b_act_all],
            [NotificationSettingsMenu.b_deact_new_search],
            [NotificationSettingsMenu.b_deact_stat_change],
            [NotificationSettingsMenu.b_act_all_comments],
            [NotificationSettingsMenu.b_deact_inforg_com],
            [NotificationSettingsMenu.b_deact_first_post_change],
            [b_back_to_start],
        ]
    else:
        # getting the list of user notification preferences
        prefs = compose_user_preferences_message(cur, user_id)
        keyboard_notifications_flexible = [
            [NotificationSettingsMenu.b_act_all],
            [NotificationSettingsMenu.b_act_new_search],
            [NotificationSettingsMenu.b_act_stat_change],
            [NotificationSettingsMenu.b_act_all_comments],
            [NotificationSettingsMenu.b_act_inforg_com],
            [NotificationSettingsMenu.b_act_first_post_change],
            [b_back_to_start],
        ]

        for line in prefs[1]:
            if line == 'all':
                keyboard_notifications_flexible = [
                    [NotificationSettingsMenu.b_deact_all],
                    [b_back_to_start],
                ]
            elif line == 'new_searches':
                keyboard_notifications_flexible[1] = [NotificationSettingsMenu.b_deact_new_search]
            elif line == 'status_changes':
                keyboard_notifications_flexible[2] = [NotificationSettingsMenu.b_deact_stat_change]
            elif line == 'comments_changes':
                keyboard_notifications_flexible[3] = [NotificationSettingsMenu.b_deact_all_comments]
            elif line == 'inforg_comments':
                keyboard_notifications_flexible[4] = [NotificationSettingsMenu.b_deact_inforg_com]
            elif line == 'first_post_changes':
                keyboard_notifications_flexible[5] = [NotificationSettingsMenu.b_deact_first_post_change]

    reply_markup = ReplyKeyboardMarkup(keyboard_notifications_flexible, resize_keyboard=True)
    return bot_message, reply_markup
