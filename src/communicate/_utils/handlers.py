import datetime
import logging

from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from _dependencies.commons import get_app_config
from _dependencies.misc import process_sending_message_async

from .buttons import (
    Commands,
    MainMenu,
    MainSettingsMenu,
    NotificationSettingsMenu,
    OtherMenu,
    RoleChoice,
    UrgencySettings,
    b_act_titles,
    b_back_to_start,
    b_coords_auto_def,
    b_coords_check,
    b_coords_del,
    b_coords_man_def,
    b_fed_dist_pick_other,
    b_menu_set_region,
    b_orders_done,
    b_orders_tbd,
    b_reg_moscow,
    b_reg_not_moscow,
    dict_of_fed_dist,
    keyboard_fed_dist_set,
    reply_markup_main,
)
from .database import (
    add_user_sys_role,
    compose_msg_on_user_setting_fullness,
    compose_user_preferences_message,
    delete_user_coordinates,
    delete_user_sys_role,
    generate_yandex_maps_place_link,
    get_search_follow_mode,
    save_preference,
    save_user_pref_role,
    save_user_pref_topic_type,
    save_user_pref_urgency,
    set_search_follow_mode,
    show_user_coordinates,
    update_and_download_list_of_regions,
)
from .services import (
    compose_full_message_on_list_of_searches,
    compose_full_message_on_list_of_searches_ikb,
    inline_processing,
    make_api_call,
    manage_age,
    manage_if_moscow,
    manage_search_follow_mode,
    process_response_of_api_call,
    save_onboarding_step,
)


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


def handle_goto_community():
    bot_message = (
        'Бот можно обсудить с соотрядниками в '
        '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате '
        'в телеграм</a>. Там можно предложить свои идеи, указать на проблемы '
        'и получить быструю обратную связь от разработчика.'
    )
    keyboard_other = [
        [OtherMenu.b_view_latest_searches],
        [OtherMenu.b_goto_first_search],
        [OtherMenu.b_goto_photos],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)
    return bot_message, reply_markup


def handle_first_search():
    bot_message = (
        'Если вы хотите стать добровольцем ДПСО «ЛизаАлерт», пожалуйста, '
        '<a href="https://lizaalert.org/forum/viewtopic.php?t=56934">'
        'посетите страницу форума</a>, там можно ознакомиться с базовой информацией '
        'для новичков и задать свои вопросы.'
        'Если вы готовитесь к своему первому поиску – приглашаем '
        '<a href="https://xn--b1afkdgwddgp9h.xn--p1ai/">ознакомиться с основами '
        'работы ЛА</a>. Всю теорию работы ЛА необходимо получать от специально '
        'обученных волонтеров ЛА. Но если у вас еще не было возможности пройти '
        'официальное обучение, а вы уже готовы выехать на поиск – этот ресурс '
        'для вас.'
    )
    keyboard_other = [
        [OtherMenu.b_view_latest_searches],
        [OtherMenu.b_goto_community],
        [OtherMenu.b_goto_photos],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)
    return bot_message, reply_markup


def handle_photos():
    bot_message = (
        'Если вам хочется окунуться в атмосферу ПСР, приглашаем в замечательный '
        '<a href="https://t.me/+6LYNNEy8BeI1NGUy">телеграм-канал с красивыми фото с '
        'поисков</a>. Все фото – сделаны поисковиками во время настоящих ПСР.'
    )
    keyboard_other = [
        [OtherMenu.b_view_latest_searches],
        [OtherMenu.b_goto_community],
        [OtherMenu.b_goto_first_search],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)
    return bot_message, reply_markup


def handle_start(bot_token, user_id, user_is_new):
    if user_is_new:
        # FIXME – 02.12.2023 – hiding menu button for the newcomers
        #  (in the future it should be done in manage_user script)
        method = 'setMyCommands'
        params = {'commands': [], 'scope': {'type': 'chat', 'chat_id': user_id}}
        response = make_api_call(method=method, bot_api_token=bot_token, params=params, call_context='if user_is_new')
        result = process_response_of_api_call(user_id, response)
        logging.info(f'hiding user {user_id} menu status = {result}')
        # FIXME ^^^

        bot_message = (
            'Привет! Это Бот Поисковика ЛизаАлерт. Он помогает Поисковикам '
            'оперативно получать информацию о новых поисках или об изменениях '
            'в текущих поисках.'
            '\n\nБот управляется кнопками, которые заменяют обычную клавиатуру. '
            'Если кнопки не отображаются, справа от поля ввода сообщения '
            'есть специальный значок, чтобы отобразить кнопки управления ботом.'
            '\n\nДавайте настроим бот индивидуально под вас. Пожалуйста, '
            'укажите вашу роль сейчас?'
        )
        keyboard_role = [
            [RoleChoice.b_role_iam_la],
            [RoleChoice.b_role_want_to_be_la],
            [RoleChoice.b_role_looking_for_person],
            [RoleChoice.b_role_other],
            [RoleChoice.b_role_secret],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard_role, resize_keyboard=True)

    else:
        bot_message = 'Привет! Бот управляется кнопками, которые заменяют обычную клавиатуру.'
        reply_markup = reply_markup_main
    return bot_message, reply_markup


def handle_finish_onboarding(cur, bot_token, got_message, username, user_id, user_role):
    method = 'deleteMyCommands'
    params = {'scope': {'type': 'chat', 'chat_id': user_id}}
    response = make_api_call(method=method, bot_api_token=bot_token, params=params)
    result = process_response_of_api_call(user_id, response)
    # FIXME ^^^

    bot_message = (
        '🎉 Отлично, вы завершили базовую настройку Бота.\n\n'
        'Список того, что сейчас умеет бот:\n'
        '- Высылает сводку по идущим поискам\n'
        '- Высылает сводку по последним поисками\n'
        '- Информирует о новых поисках с указанием расстояния до поиска\n'
        '- Информирует об изменении Статуса / Первого поста Инфорга\n'
        '- Информирует о новых комментариях Инфорга или пользователей\n'
        '- Позволяет гибко настроить информирование на основе удаленности от '
        'вас, возраста пропавшего и т.п.\n\n'
        'С этого момента вы начнёте получать основные уведомления в '
        'рамках выбранного региона, как только появятся новые изменения. '
        'Или же вы сразу можете просмотреть списки Активных и Последних поисков.\n\n'
        'Бот приглашает вас настроить дополнительные параметры (можно пропустить):\n'
        '- Настроить виды уведомлений\n'
        '- Указать домашние координаты\n'
        '- Указать максимальный радиус до поиска\n'
        '- Указать возрастные группы пропавших\n'
        '- Связать бот с Форумом\n\n'
        'Создатели Бота надеются, что Бот сможет помочь вам в ваших задачах! Удачи!'
    )

    keyboard_role = [
        [MainSettingsMenu.b_set_pref_notif_type],
        [MainSettingsMenu.b_set_pref_coords],
        [MainSettingsMenu.b_set_pref_radius],
        [MainSettingsMenu.b_set_pref_age],
        [MainSettingsMenu.b_set_forum_nick],
        [OtherMenu.b_view_latest_searches],
        [MainMenu.b_view_act_searches],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard_role, resize_keyboard=True)

    if got_message == b_reg_moscow:
        bot_message, reply_markup = manage_if_moscow(
            cur,
            user_id,
            username,
            got_message,
            b_reg_moscow,
            b_reg_not_moscow,
            reply_markup,
            keyboard_fed_dist_set,
            bot_message,
            user_role,
        )
    else:
        save_onboarding_step(user_id, username, 'region_set')
        save_user_pref_topic_type(cur, user_id, 'default', user_role)
        updated_regions = update_and_download_list_of_regions(
            cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
        )
    return bot_message, reply_markup


def handle_role_select(cur, got_message, username, user_id):
    if got_message in RoleChoice.list():
        user_role = save_user_pref_role(cur, user_id, got_message)
        save_onboarding_step(user_id, username, 'role_set')

        # get user role = relatives looking for a person
    if got_message == RoleChoice.b_role_looking_for_person:
        bot_message = (
            'Тогда вам следует:\n\n'
            '1. Подайте заявку на поиск в ЛизаАлерт ОДНИМ ИЗ ДВУХ способов:\n'
            '  1.1. САМОЕ БЫСТРОЕ – звоните на 88007005452 (бесплатная горячая '
            'линия ЛизаАлерт). Вам зададут ряд вопросов, который максимально '
            'ускорит поиск, и посоветуют дальнейшие действия. \n'
            '  1.2. Заполните форму поиска https://lizaalert.org/zayavka-na-poisk/ \n'
            'После заполнения формы на сайте нужно ожидать звонка от ЛизаАлерт. На '
            'обработку может потребоваться более часа. Если нет возможности ждать, '
            'после заполнения заявки следует позвонить на горячую линию отряда '
            '88007005452, сообщив, что вы уже оформили заявку на сайте.\n\n'
            '2. Подать заявление в Полицию. Если иное не посоветовали на горячей линии,'
            'заявка в Полицию – поможет ускорить и упростить поиск. Самый быстрый '
            'способ – позвонить на 102.\n\n'
            '3. Отслеживайте ход поиска.\n'
            'Когда заявки в ЛизаАлерт и Полицию сделаны, отряд начнет первые '
            'мероприятия для поиска человека: уточнение деталей, прозвоны '
            'в госучреждения, формирование плана и команды поиска и т.п. Весь этот'
            'процесс вам не будет виден, но часто люди находятся именно на этой стадии'
            'поиска. Если первые меры не помогут и отряд примет решение проводить'
            'выезд "на место поиска" – тогда вы сможете отслеживать ход поиска '
            'через данный Бот, для этого продолжите настройку бота: вам нужно будет'
            'указать ваш регион и выбрать, какие уведомления от бота вы будете '
            'получать. '
            'Как альтернатива, вы можете зайти на форум https://lizaalert.org/forum/, '
            'и отслеживать статус поиска там.\n'
            'Отряд сделает всё возможное, чтобы найти вашего близкого как можно '
            'скорее.\n\n'
            'Сообщите, подали ли вы заявки в ЛизаАлерт и Полицию?'
        )

        keyboard_orders = [[b_orders_done], [b_orders_tbd]]
        reply_markup = ReplyKeyboardMarkup(keyboard_orders, resize_keyboard=True)

        # get user role = potential LA volunteer
    elif got_message == RoleChoice.b_role_want_to_be_la:
        bot_message = (
            'Супер! \n'
            'Знаете ли вы, как можно помогать ЛизаАлерт? Определились ли вы, как '
            'вы готовы помочь? Если еще нет – не беда – рекомендуем '
            'ознакомиться со статьёй: '
            'https://takiedela.ru/news/2019/05/25/instrukciya-liza-alert/\n\n'
            'Задачи, которые можно выполнять даже без специальной подготовки, '
            'выполняют Поисковики "на месте поиска". Этот Бот как раз старается '
            'помогать именно Поисковикам. '
            'Есть хороший сайт, рассказывающий, как начать участвовать в поиске: '
            'https://xn--b1afkdgwddgp9h.xn--p1ai/\n\n'
            'В случае любых вопросов – не стесняйтесь, обращайтесь на общий телефон, '
            '8 800 700-54-52, где вам помогут с любыми вопросами при вступлении в отряд.\n\n'
            'А если вы "из мира IT" и готовы помогать развитию этого Бота,'
            'пишите нам в специальный чат https://t.me/+2J-kV0GaCgwxY2Ni\n\n'
            'Надеемся, эта информацию оказалась полезной. '
            'Если вы готовы продолжить настройку Бота, уточните, пожалуйста: '
            'ваш основной регион – это Москва и Московская Область?'
        )
        keyboard_coordinates_admin = [[b_reg_moscow], [b_reg_not_moscow]]
        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

        # get user role = all others
    elif got_message in {
        RoleChoice.b_role_iam_la,
        RoleChoice.b_role_other,
        RoleChoice.b_role_secret,
        b_orders_done,
        b_orders_tbd,
    }:
        bot_message = 'Спасибо. Теперь уточните, пожалуйста, ваш основной регион – это ' 'Москва и Московская Область?'
        keyboard_coordinates_admin = [[b_reg_moscow], [b_reg_not_moscow]]
        reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)
    return bot_message, reply_markup, user_role


def handle_no_help():
    bot_message = (
        'Спасибо, понятно. Мы записали. Тогда бот более не будет вас беспокоить, '
        'пока вы сами не напишите в бот.\n\n'
        'На прощание, бот хотел бы посоветовать следующие вещи, делающие мир лучше:\n\n'
        '1. Посмотреть <a href="https://t.me/+6LYNNEy8BeI1NGUy">позитивные фото '
        'с поисков ЛизаАлерт</a>.\n\n'
        '2. <a href="https://lizaalert.org/otryadnye-nuzhdy/">Помочь '
        'отряду ЛизаАлерт, пожертвовав оборудование для поисков людей</a>.\n\n'
        '3. Помочь создателям данного бота, присоединившись к группе разработчиков'
        'или оплатив облачную инфраструктуру для бесперебойной работы бота. Для этого'
        '<a href="https://t.me/MikeMikeT">просто напишите разработчику бота</a>.\n\n'
        'Бот еще раз хотел подчеркнуть, что как только вы напишите что-то в бот – он'
        'сразу же "забудет", что вы ранее просили вас не беспокоить:)\n\n'
        'Обнимаем:)'
    )
    keyboard = [[b_back_to_start]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    return bot_message, reply_markup


def handle_help_message():
    bot_message = (
        'Супер! Тогда давайте посмотрим, что у вас не настроено.\n\n'
        'У вас не настроен Регион поисков – без него Бот не может определить, '
        'какие поиски вас интересуют. Вы можете настроить регион двумя способами:\n'
        '1. Либо автоматически на основании ваших координат – нужно будет отправить '
        'вашу геолокацию (работает только с мобильных устройств),\n'
        '2. Либо выбрав регион вручную: для этого нужно сначала выбрать ФО = '
        'Федеральный Округ, где находится ваш регион, а потом кликнуть на сам регион. '
        '\n\n'
    )
    return bot_message, None


def handle_surgency_settings(cur, got_message, user_id):
    save_user_pref_urgency(
        cur,
        user_id,
        got_message,
        UrgencySettings.b_pref_urgency_highest,
        UrgencySettings.b_pref_urgency_high,
        UrgencySettings.b_pref_urgency_medium,
        UrgencySettings.b_pref_urgency_low,
    )
    bot_message = 'Хорошо, спасибо. Бот запомнил ваш выбор.'
    return bot_message, None


def handle_set_region_2(user_id):
    bot_message = (
        'Для корректной работы бота, пожалуйста, задайте свой регион. Для этого '
        'с помощью кнопок меню выберите сначала ФО (федеральный округ), а затем и '
        'регион. Можно выбирать несколько регионов из разных ФО. Выбор региона '
        'также можно отменить, повторно нажав на кнопку с названием региона. '
        'Функционал бота не будет активирован, пока не выбран хотя бы один регион.'
    )

    keyboard_coordinates_admin = [[b_menu_set_region]]
    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

    logging.info(f'user {user_id} is forced to fill in the region')
    return bot_message, reply_markup


def handle_search_mode_on_off(cur, bot_token, user_id, got_callback, callback_query_id, callback_query):
    bot_message = manage_search_follow_mode(cur, user_id, got_callback, callback_query_id, callback_query, bot_token)
    reply_markup = reply_markup_main
    return bot_message, reply_markup


def handle_view_searches(cur, bot_token, got_message, user_id, user_regions, bot_message, reply_markup):
    msg_sent_by_specific_code = True

    temp_dict = {
        OtherMenu.b_view_latest_searches: 'all',
        MainMenu.b_view_act_searches: 'active',
        Commands.c_view_latest_searches: 'all',
        Commands.c_view_act_searches: 'active',
    }

    cur.execute(
        """
            SELECT folder_id, folder_display_name FROM geo_folders_view WHERE folder_type='searches';
            """
    )

    folders_list = cur.fetchall()

    if get_search_follow_mode(cur, user_id):
        # issue#425 make inline keyboard - list of searches
        keyboard = []  # to combine monolit ikb for all user's regions
        ikb_searches_count = 0

        region_name = ''
        for region in user_regions:
            for line in folders_list:
                if line[0] == region:
                    region_name = line[1]
                    break

            logging.info(f'Before if region_name.find...: {bot_message=}; {keyboard=}')
            # check if region – is an archive folder: if so – it can be sent only to 'all'
            if region_name.find('аверш') == -1 or temp_dict[got_message] == 'all':
                new_region_ikb_list = compose_full_message_on_list_of_searches_ikb(
                    cur, temp_dict[got_message], user_id, region, region_name
                )
                keyboard.append(new_region_ikb_list)
                ikb_searches_count += len(new_region_ikb_list) - 1  ##number of searches in the region
                logging.info(f'After += compose_full_message_on_list_of_searches_ikb: {keyboard=}')

            ##msg_sent_by_specific_code for combined ikb start
        if ikb_searches_count == 0:
            bot_message = 'Незавершенные поиски в соответствии с Вашей настройкой видов поисков не найдены.'
            params = {
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
                'reply_markup': reply_markup,
                'chat_id': user_id,
                'text': bot_message,
            }
            context = f'{user_id=}, context_step=b1'
            response = make_api_call('sendMessage', bot_token, params, context)
            logging.info(f'{response=}; {user_id=}; context_step=b2')
            result = process_response_of_api_call(user_id, response)
            logging.info(f'{result=}; {user_id=}; context_step=b3')
            inline_processing(cur, response, params)
        else:
            # issue#425 show the inline keyboard
            ##TBD. May be will be useful to show quantity of marked searches
            #                        searches_marked = 0
            #                        for region_keyboard in keyboard:
            #                            for ikb_line in region_keyboard:
            #                                if ikb_line[0].get("callback_data") and not ikb_line[0]["text"][:1]=='  ':
            #                                    searches_marked += 1
            for i, region_keyboard in enumerate(keyboard):
                if i == 0:
                    bot_message = """МЕНЮ АКТУАЛЬНЫХ ПОИСКОВ ДЛЯ ОТСЛЕЖИВАНИЯ.
Каждый поиск ниже дан строкой из пары кнопок: кнопка пометки для отслеживания и кнопка перехода на форум.
👀 - знак пометки поиска для отслеживания, уведомления будут приходить только по помеченным поискам. 
Если таких нет, то уведомления будут приходить по всем поискам согласно настройкам.
❌ - пометка поиска для игнорирования ("черный список") - уведомления по таким поискам не будут приходить в любом случае."""
                else:
                    bot_message = ''

                    # Pop region caption from the region_keyboard and put it into bot-message
                bot_message += '\n' if len(bot_message) > 0 else ''
                bot_message += f'<a href="{region_keyboard[0][0]["url"]}">{region_keyboard[0][0]["text"]}</a>'
                region_keyboard.pop(0)

                if i == (len(keyboard) - 1):
                    region_keyboard += [
                        [
                            {
                                'text': 'Отключить выбор поисков для отслеживания',
                                'callback_data': '{"action":"search_follow_mode_off"}',
                            }
                        ]
                    ]

                reply_markup = InlineKeyboardMarkup(region_keyboard)
                logging.info(f'{bot_message=}; {region_keyboard=}; context_step=b00')
                # process_sending_message_async(user_id=user_id, data=data)
                context = (
                    f'Before if reply_markup and not isinstance(reply_markup, dict): {reply_markup=}, context_step=b01'
                )
                logging.info(f'{context=}: {reply_markup=}')
                if reply_markup and not isinstance(reply_markup, dict):
                    reply_markup = reply_markup.to_dict()
                    context = f'After reply_markup.to_dict(): {reply_markup=}; {user_id=}; context_step=b02a'
                    logging.info(f'{context=}: {reply_markup=}')

                params = {
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True,
                    'reply_markup': reply_markup,
                    'chat_id': user_id,
                    'text': bot_message,
                }
                context = f'{user_id=}, context_step=b1'
                response = make_api_call('sendMessage', bot_token, params, context)
                logging.info(f'{response=}; {user_id=}; context_step=b2')
                result = process_response_of_api_call(user_id, response)
                logging.info(f'{result=}; {user_id=}; context_step=b3')
                inline_processing(cur, response, params)
            ##msg_sent_by_specific_code for combined ikb end

            # saving the last message from bot
        try:
            cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))
            cur.execute(
                'INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);',
                (user_id, datetime.datetime.now(), 'report'),
            )
        except Exception as e:
            logging.info('failed to save the last message from bot')
            logging.exception(e)

    else:
        region_name = ''
        for region in user_regions:
            for line in folders_list:
                if line[0] == region:
                    region_name = line[1]
                    break

                # check if region – is an archive folder: if so – it can be sent only to 'all'
            if region_name.find('аверш') == -1 or temp_dict[got_message] == 'all':
                bot_message = compose_full_message_on_list_of_searches(
                    cur, temp_dict[got_message], user_id, region, region_name
                )
                reply_markup = reply_markup_main
                data = {
                    'text': bot_message,
                    'reply_markup': reply_markup,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True,
                }
                process_sending_message_async(user_id=user_id, data=data)

                # saving the last message from bot
                try:
                    cur.execute("""DELETE FROM msg_from_bot WHERE user_id=%s;""", (user_id,))
                    cur.execute(
                        'INSERT INTO msg_from_bot (user_id, time, msg_type) values (%s, %s, %s);',
                        (user_id, datetime.datetime.now(), 'report'),
                    )
                except Exception as e:
                    logging.info('failed to save the last message from bot')
                    logging.exception(e)
            # issue425 Button for turn on search following mode
        try:
            search_follow_mode_ikb = [
                [
                    {
                        'text': 'Включить выбор поисков для отслеживания',
                        'callback_data': '{"action":"search_follow_mode_on"}',
                    }
                ]
            ]
            reply_markup = InlineKeyboardMarkup(search_follow_mode_ikb)
            if reply_markup and not isinstance(reply_markup, dict):
                reply_markup = reply_markup.to_dict()
                context = f'After reply_markup.to_dict(): {reply_markup=}; {user_id=}; context_step=a00'
                logging.info(f'{context=}: {reply_markup=}')
            params = {
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
                'reply_markup': reply_markup,
                'chat_id': user_id,
                'text': """Вы можете включить возможность выбора поисков для отслеживания, 
чтобы получать уведомления не со всех актуальных поисков, 
а только с выбранных Вами.""",
            }
            context = f'{user_id=}, context_step=a01'
            response = make_api_call('sendMessage', bot_token, params, context)
            logging.info(f'{response=}; {user_id=}; context_step=a02')
            result = process_response_of_api_call(user_id, response)
            logging.info(f'{result=}; {user_id=}; context_step=a03')
            inline_processing(cur, response, params)
        except Exception as e:
            logging.info('failed to show button for turn on search following mode')
            logging.exception(e)
    return bot_message, reply_markup, msg_sent_by_specific_code


def handle_admin_menu():
    bot_message = 'Вы вошли в специальный тестовый админ-раздел'

    # keyboard for Home Coordinates sharing
    keyboard_coordinates_admin = [[b_back_to_start], [b_back_to_start]]
    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)
    return bot_message, reply_markup


def handle_start_testing(cur, user_id):
    add_user_sys_role(cur, user_id, 'tester')
    bot_message = (
        'Вы в секретном тестовом разделе, где всё может работать не так :) '
        'Если что – пишите, пожалуйста, в телеграм-чат '
        'https://t.me/joinchat/2J-kV0GaCgwxY2Ni'
        '\n💡 А еще Вам добавлена роль tester - некоторые тестовые функции включены автоматически.'
        '\nДля отказа от роли tester нужно отправить команду notest'
    )
    # keyboard_coordinates_admin = [[b_set_topic_type], [b_back_to_start]]
    # [b_set_pref_urgency], [b_set_forum_nick]

    map_button = {'text': 'Открыть карту поисков', 'web_app': {'url': get_app_config().web_app_url_test}}
    keyboard = [[map_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return bot_message, reply_markup


def handle_leave_testing(cur, user_id):
    delete_user_sys_role(cur, user_id, 'tester')
    bot_message = 'Роль tester удалена. Приходите еще! :-) Возвращаемся в главное меню.'
    reply_markup = reply_markup_main
    return bot_message, reply_markup


def handle_off_search_mode(cur, user_id):
    set_search_follow_mode(cur, user_id, False)
    bot_message = 'Возможность отслеживания поисков вЫключена. Возвращаемся в главное меню.'
    reply_markup = reply_markup_main
    return bot_message, reply_markup


def handle_map_open():
    bot_message = (
        'В Боте Поисковика теперь можно посмотреть 🗺️Карту Поисков📍.\n\n'
        'На карте вы сможете увидеть все активные поиски, '
        'построить к каждому из них маршрут с учетом пробок, '
        'а также открыть этот маршрут в сервисах Яндекс.\n\n'
        'Карта работает в тестовом режиме.\n'
        'Если карта будет работать некорректно, или вы видите, как ее необходимо '
        'доработать – напишите в '
        '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">чат разработчиков</a>.'
        ''
    )

    map_button = {'text': 'Открыть карту поисков', 'web_app': {'url': get_app_config().web_app_url}}
    keyboard = [[map_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return bot_message, reply_markup


def handle_age_preferences(cur, got_message, user_id):
    input_data = None if got_message == MainSettingsMenu.b_set_pref_age else got_message
    keyboard, first_visit = manage_age(cur, user_id, input_data)
    keyboard.append([b_back_to_start])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if got_message.lower() == MainSettingsMenu.b_set_pref_age:
        bot_message = (
            'Чтобы включить или отключить уведомления по определенной возрастной '
            'группе, нажмите на неё. Настройку можно изменить в любой момент.'
        )
        if first_visit:
            bot_message = (
                'Данное меню позволяет выбрать возрастные категории БВП '
                '(без вести пропавших), по которым вы хотели бы получать уведомления. '
                'Важно, что если бот не сможет распознать возраст БВП, тогда вы '
                'всё равно получите уведомление.\nТакже данная настройка не влияет на '
                'разделы Актуальные Поиски и Последние Поиски – в них вы всё также '
                'сможете увидеть полный список поисков.\n\n' + bot_message
            )
    else:
        bot_message = 'Спасибо, записали.'
    return bot_message, reply_markup


def handle_set_urgency_1():
    bot_message = (
        'Очень многие поисковики пользуются этим Ботом. При любой рассылке нотификаций'
        ' Бот ставит все сообщения в очередь, и они обрабатываются '
        'со скоростью, ограниченной технологиями Телеграма. Иногда, в случае нескольких'
        ' больших поисков, очередь вырастает и кто-то получает сообщения практически '
        'сразу, а кому-то они приходят с задержкой.\n'
        'Вы можете помочь сделать рассылки уведомлений более "нацеленными", обозначив '
        'с какой срочностью вы бы хотели получать уведомления от Бота. В скобках '
        'указаны примерные сроки задержки относительно появления информации на форуме. '
        'Выберите наиболее подходящий Вам вариант'
    )
    keyboard = [
        [UrgencySettings.b_pref_urgency_highest],
        [UrgencySettings.b_pref_urgency_high],
        [UrgencySettings.b_pref_urgency_medium],
        [UrgencySettings.b_pref_urgency_low],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    return bot_message, reply_markup


def handle_other_menu(keyboard_other):
    bot_message = (
        'Здесь можно посмотреть статистику по 20 последним поискам, перейти в '
        'канал Коммъюнити или Прочитать важную информацию для Новичка и посмотреть '
        'душевные фото с поисков'
    )
    reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)
    return bot_message, reply_markup


def handle_set_region(cur, got_message, user_id):
    bot_message = update_and_download_list_of_regions(
        cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
    )
    reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)
    return bot_message, reply_markup


def handle_federal_district(cur, got_message, user_id):
    updated_regions = update_and_download_list_of_regions(
        cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
    )
    bot_message = updated_regions
    reply_markup = ReplyKeyboardMarkup(dict_of_fed_dist[got_message], resize_keyboard=True)
    return bot_message, reply_markup


def handle_full_dict_of_regions(cur, got_message, username, user_id, onboarding_step_id, user_role):
    updated_regions = update_and_download_list_of_regions(
        cur, user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
    )
    bot_message = updated_regions
    keyboard = keyboard_fed_dist_set
    for fed_dist in dict_of_fed_dist:
        for region in dict_of_fed_dist[fed_dist]:
            if region[0] == got_message:
                keyboard = dict_of_fed_dist[fed_dist]
                break
        else:
            continue
        break
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if onboarding_step_id == 20:  # "moscow_replied"
        save_onboarding_step(user_id, username, 'region_set')
        save_user_pref_topic_type(cur, user_id, 'default', user_role)
    return bot_message, reply_markup


def handle_settings_menu(cur, user_id):
    bot_message = (
        'Это раздел с настройками. Здесь вы можете выбрать удобные для вас '
        'уведомления, а также ввести свои "домашние координаты", на основе которых '
        'будет рассчитываться расстояние и направление до места поиска. Вы в любой '
        'момент сможете изменить эти настройки.'
    )

    message_prefix = compose_msg_on_user_setting_fullness(cur, user_id)
    if message_prefix:
        bot_message = f'{bot_message}\n\n{message_prefix}'

    keyboard_settings = [
        [MainSettingsMenu.b_set_pref_notif_type],
        [b_menu_set_region],
        [MainSettingsMenu.b_set_topic_type],
        [MainSettingsMenu.b_set_pref_coords],
        [MainSettingsMenu.b_set_pref_radius],
        [MainSettingsMenu.b_set_pref_age],
        [MainSettingsMenu.b_set_forum_nick],
        [b_back_to_start],
    ]  # #AK added b_set_forum_nick for issue #6
    reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)
    return bot_message, reply_markup


def handle_set_pref_coordinates():
    bot_message = (
        'АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ координат работает только для носимых устройств'
        ' (для настольных компьютеров – НЕ работает: используйте, пожалуйста, '
        'кнопку ручного ввода координат). '
        'При автоматическом определении координат – нажмите на кнопку и '
        'разрешите определить вашу текущую геопозицию. '
        'Координаты, загруженные вручную или автоматически, будут считаться '
        'вашим "домом", откуда будут рассчитаны расстояние и '
        'направление до поисков.'
    )
    keyboard_coordinates_1 = [
        [b_coords_auto_def],
        [b_coords_man_def],
        [b_coords_check],
        [b_coords_del],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)
    return bot_message, reply_markup


def handle_coordinates_deletion(cur, user_id):
    delete_user_coordinates(cur, user_id)
    bot_message = (
        'Ваши "домашние координаты" удалены. Теперь расстояние и направление '
        'до поисков не будет отображаться.\n'
        'Вы в любой момент можете заново ввести новые "домашние координаты". '
        'Функция Автоматического определения координат работает только для '
        'носимых устройств, для настольного компьютера – воспользуйтесь '
        'ручным вводом.'
    )
    keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check], [b_back_to_start]]
    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)
    return bot_message, reply_markup


def handle_coordinates_1():
    bot_message = (
        'Введите координаты вашего дома вручную в теле сообщения и просто '
        'отправьте. Формат: XX.XXXХХ, XX.XXXХХ, где количество цифр после точки '
        'может быть различным. Широта (первое число) должна быть между 30 '
        'и 80, Долгота (второе число) – между 10 и 190.'
    )
    bot_request_aft_usr_msg = 'input_of_coords_man'
    reply_markup = ReplyKeyboardRemove()
    return bot_message, reply_markup, bot_request_aft_usr_msg


def handle_coordinates_check(cur, user_id):
    lat, lon = show_user_coordinates(cur, user_id)
    if lat and lon:
        bot_message = 'Ваши "домашние координаты" '
        bot_message += generate_yandex_maps_place_link(lat, lon, 'coords')

    else:
        bot_message = 'Ваши координаты пока не сохранены. Введите их автоматически или вручную.'

    keyboard_coordinates_1 = [
        [b_coords_auto_def],
        [b_coords_man_def],
        [b_coords_check],
        [b_coords_del],
        [b_back_to_start],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)
    return bot_message, reply_markup
