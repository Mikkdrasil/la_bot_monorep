import hashlib
from enum import Enum
from typing import Any, Dict

full_buttons_dict = {
    'topic_types': {
        'regular': {'text': 'стандартные активные поиски', 'id': 0},
        'resonance': {'text': 'резонансные поиски', 'id': 5, 'hide': False},
        'info_support': {'text': 'информационная поддержка', 'id': 4, 'hide': False},
        'reverse': {'text': 'обратные поиски', 'id': 1},
        'training': {'text': 'учебные поиски', 'id': 3},
        'patrol': {'text': 'ночной патруль', 'id': 2, 'hide': False},
        'event': {'text': 'мероприятия', 'id': 10},
        'info': {'text': 'полезная информация', 'id': 20, 'hide': True},
        'about': {'text': '💡 справка по типам поисков 💡', 'id': None},
    },
    'roles': {
        'member': {'text': 'я состою в ЛизаАлерт', 'id': 'member'},
        'new_member': {'text': 'я хочу помогать ЛизаАлерт', 'id': 'new_member'},
        'relative': {'text': 'я ищу человека', 'id': 'relative'},
        'other': {'text': 'у меня другая задача', 'id': 'other'},
        'no_answer': {'text': 'не хочу говорить', 'id': 'no_answer'},
        'about': {'text': '💡 справка по ролям 💡', 'id': None},
    },
    'set': {'topic_type': {'text': 'настроить вид поисков', 'id': 'topic_type'}},
    'core': {'to_start': {'text': 'в начало', 'id': 'to_start'}},
}


def search_button_row_ikb(search_following_mode, search_status, search_id, search_display_name, url):
    search_following_mark = search_following_mode if search_following_mode else '  '
    ikb_row = [
        [
            {
                'text': f'{search_following_mark} {search_status}',
                'callback_data': f'{{"action":"search_follow_mode", "hash":"{search_id}"}}',
            },  ##left button to on/off follow
            {'text': search_display_name, 'url': url},  ##right button - link to the search on the forum
        ]
    ]
    return ikb_row


class GroupOfButtons:
    """Contains the set of unique buttons of the similar nature (to be shown together as alternatives)"""

    def __init__(
        self,
        button_dict,
        modifier_dict=None,
    ):
        self.modifier_dict = modifier_dict

        all_button_texts = []
        all_button_hashes = []
        for key, value in button_dict.items():
            setattr(self, key, Button(value, modifier_dict))
            all_button_texts += self.__getattribute__(key).any_text
            all_button_hashes.append(self.__getattribute__(key).hash)
        self.any_text = all_button_texts
        self.any_hash = all_button_hashes

    def __str__(self):
        return self.any_text

    def contains(self, check: str) -> bool:
        """Check is the given text/hash is used for any button in this group"""

        if check in self.any_text:
            return True

        if check in self.any_hash:
            return True

        return False

    def temp_all_keys(self):
        return [k for k, v in self.__dict__.items()]

    def id(self, given_id):
        """Return a Button which correspond to the given id"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'id') and value.id == given_id:
                return value
        return None

    def keyboard(self, act_list, change_list):
        """Generate a list of telegram buttons (2D array) basing on existing setting list and one that should change"""

        keyboard = []
        for key, value in self.__dict__.items():
            curr_button = self.__getattribute__(key)
            if key in {'modifier_dict', 'any_text', 'any_hash'}:
                continue
            if hasattr(value, 'hide') and value.hide:
                continue
            curr_button_is_in_existing_id_list = False
            curr_button_is_asked_to_change = False
            for id_item in act_list:
                if curr_button.id == id_item:
                    curr_button_is_in_existing_id_list = True
                    break
            for id_item in change_list:
                if curr_button.id == id_item:
                    curr_button_is_asked_to_change = True
                    break

            if curr_button_is_in_existing_id_list and key not in {'about'}:
                if not curr_button_is_asked_to_change:
                    keyboard += [
                        {'text': curr_button.on, 'callback_data': f'{{"action":"off","hash": "{curr_button.hash}"}}'}
                    ]
                else:
                    keyboard += [
                        {'text': curr_button.off, 'callback_data': f'{{"action":"on","hash": "{curr_button.hash}"}}'}
                    ]
            elif key not in {'about'}:
                if not curr_button_is_asked_to_change:
                    keyboard += [
                        {'text': curr_button.off, 'callback_data': f'{{"action":"on","hash": "{curr_button.hash}"}}'}
                    ]
                else:
                    keyboard += [
                        {'text': curr_button.on, 'callback_data': f'{{"action":"off","hash": "{curr_button.hash}"}}'}
                    ]
            else:  # case for 'about' button
                keyboard += [
                    {'text': curr_button.text, 'callback_data': f'{{"action":"about","hash": "{curr_button.hash}"}}'}
                ]

        keyboard = [[k] for k in keyboard]

        return keyboard

    def button_by_text(self, given_text):
        """Return a Button which correspond to the given text"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'any_text') and given_text in value.any_text:
                return value
        return None

    def button_by_hash(self, given_hash):
        """Return a Button which correspond to the given hash"""
        for key, value in self.__dict__.items():
            if not value:
                continue
            if hasattr(value, 'hash') and given_hash == value.hash:
                return value
        return None


class AllButtons:
    def __init__(self, initial_dict):
        for key, value in initial_dict.items():
            setattr(self, key, GroupOfButtons(value))

    def temp_all_keys(self):
        return [k for k, v in self.__dict__.items()]


class Button:
    """Contains one unique button and all the associated attributes"""

    def __init__(self, data: Dict[str, Any] = None, modifier=None):
        if modifier is None:
            modifier = {'on': '✅ ', 'off': '☐ '}  # standard modifier

        self.modifier = modifier
        self.data = data
        self.text = None
        for key, value in self.data.items():
            setattr(self, key, value)
        self.hash = hashlib.shake_128(self.text.encode('utf-8')).hexdigest(4)  # noqa

        self.any_text = [self.text]
        for key, value in modifier.items():
            new_value = f'{value}{self.text}'
            setattr(self, key, new_value)
            self.any_text.append(new_value)

        self.all = [v for k, v in self.__dict__.items() if v != modifier]

    def __str__(self):
        return self.text

    def temp_all_keys(self):
        return [k for k, v in self.__dict__.items()]


c_start = '/start'
b_back_to_start = 'в начало'
b_fed_dist_pick_other = 'выбрать другой Федеральный Округ'


# Settings - Dalnevostochniy Fed Dist - Regions
b_reg_buryatiya = 'Бурятия'
b_reg_prim_kray = 'Приморский край'
b_reg_habarovsk = 'Хабаровский край'
b_reg_amur = 'Амурская обл.'
b_reg_dal_vost_other = 'Прочие поиски по ДФО'
keyboard_dal_vost_reg_choice = [
    [b_reg_buryatiya],
    [b_reg_prim_kray],
    [b_reg_habarovsk],
    [b_reg_amur],
    [b_reg_dal_vost_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Privolzhskiy Fed Dist - Regions
b_reg_bashkorkostan = 'Башкортостан'
b_reg_kirov = 'Кировская обл.'
b_reg_mariy_el = 'Марий Эл'
b_reg_mordovia = 'Мордовия'
b_reg_nizhniy = 'Нижегородская обл.'
b_reg_orenburg = 'Оренбургская обл.'
b_reg_penza = 'Пензенская обл.'
b_reg_perm = 'Пермский край'
b_reg_samara = 'Самарская обл.'
b_reg_saratov = 'Саратовская обл.'
b_reg_tatarstan = 'Татарстан'
b_reg_udmurtiya = 'Удмуртия'
b_reg_ulyanovsk = 'Ульяновская обл.'
b_reg_chuvashiya = 'Чувашия'
b_reg_privolz_other = 'Прочие поиски по ПФО'
keyboard_privolz_reg_choice = [
    [b_reg_bashkorkostan],
    [b_reg_kirov],
    [b_reg_mariy_el],
    [b_reg_mordovia],
    [b_reg_nizhniy],
    [b_reg_orenburg],
    [b_reg_penza],
    [b_reg_perm],
    [b_reg_samara],
    [b_reg_saratov],
    [b_reg_tatarstan],
    [b_reg_udmurtiya],
    [b_reg_ulyanovsk],
    [b_reg_chuvashiya],
    [b_reg_privolz_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]


# Settings - Severo-Kavkazskiy Fed Dist - Regions
b_reg_dagestan = 'Дагестан'
b_reg_stavropol = 'Ставропольский край'
b_reg_chechnya = 'Чечня'
b_reg_kabarda = 'Кабардино-Балкария'
b_reg_ingushetia = 'Ингушетия'
b_reg_sev_osetia = 'Северная Осетия'
b_reg_sev_kav_other = 'Прочие поиски по СКФО'
keyboard_sev_kav_reg_choice = [
    [b_reg_dagestan],
    [b_reg_stavropol],
    [b_reg_chechnya],
    [b_reg_kabarda],
    [b_reg_ingushetia],
    [b_reg_sev_osetia],
    [b_reg_sev_kav_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Severo-Zapadniy Fed Dist - Regions
b_reg_vologda = 'Вологодская обл.'
b_reg_karelia = 'Карелия'
b_reg_komi = 'Коми'
b_reg_piter = 'Ленинградская обл.'
b_reg_murmansk = 'Мурманская обл.'
b_reg_pskov = 'Псковская обл.'
b_reg_archangelsk = 'Архангельская обл.'
b_reg_sev_zap_other = 'Прочие поиски по СЗФО'
keyboard_sev_zap_reg_choice = [
    [b_reg_vologda],
    [b_reg_komi],
    [b_reg_karelia],
    [b_reg_piter],
    [b_reg_murmansk],
    [b_reg_pskov],
    [b_reg_archangelsk],
    [b_reg_sev_zap_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]


# Settings - Sibirskiy Fed Dist - Regions
b_reg_altay = 'Алтайский край'
b_reg_irkutsk = 'Иркутская обл.'
b_reg_kemerovo = 'Кемеровская обл.'
b_reg_krasnoyarsk = 'Красноярский край'
b_reg_novosib = 'Новосибирская обл.'
b_reg_omsk = 'Омская обл.'
b_reg_tomsk = 'Томская обл.'
b_reg_hakasiya = 'Хакасия'
b_reg_sibiria_reg_other = 'Прочие поиски по СФО'
keyboard_sibiria_reg_choice = [
    [b_reg_altay],
    [b_reg_irkutsk],
    [b_reg_kemerovo],
    [b_reg_krasnoyarsk],
    [b_reg_novosib],
    [b_reg_omsk],
    [b_reg_tomsk],
    [b_reg_hakasiya],
    [b_reg_sibiria_reg_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]


# Settings - Uralskiy Fed Dist - Regions
b_reg_ekat = 'Свердловская обл.'
b_reg_kurgan = 'Курганская обл.'
b_reg_tyumen = 'Тюменская обл.'
b_reg_hanty_mansi = 'Ханты-Мансийский АО'
b_reg_chelyabinks = 'Челябинская обл.'
b_reg_yamal = 'Ямало-Ненецкий АО'
b_reg_urals_reg_other = 'Прочие поиски по УФО'
keyboard_urals_reg_choice = [
    [b_reg_ekat],
    [b_reg_kurgan],
    [b_reg_tyumen],
    [b_reg_hanty_mansi],
    [b_reg_chelyabinks],
    [b_reg_yamal],
    [b_reg_urals_reg_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]


# Settings - Central Fed Dist - Regions
b_reg_belogorod = 'Белгородская обл.'
b_reg_bryansk = 'Брянская обл.'
b_reg_vladimir = 'Владимирская обл.'
b_reg_voronezh = 'Воронежская обл.'
b_reg_ivanovo = 'Ивановская обл.'
b_reg_kaluga = 'Калужская обл.'
b_reg_kostroma = 'Костромская обл.'
b_reg_kursk = 'Курская обл.'
b_reg_lipetsk = 'Липецкая обл.'
b_reg_msk_act = 'Москва и МО: Активные Поиски'
b_reg_msk_inf = 'Москва и МО: Инфо Поддержка'
b_reg_orel = 'Орловская обл.'
b_reg_ryazan = 'Рязанская обл.'
b_reg_smolensk = 'Смоленская обл.'
b_reg_tambov = 'Тамбовская обл.'
b_reg_tver = 'Тверская обл.'
b_reg_tula = 'Тульская обл.'
b_reg_yaroslavl = 'Ярославская обл.'
b_reg_central_reg_other = 'Прочие поиски по ЦФО'
keyboard_central_reg_choice = [
    [b_reg_belogorod],
    [b_reg_bryansk],
    [b_reg_vladimir],
    [b_reg_voronezh],
    [b_reg_ivanovo],
    [b_reg_kaluga],
    [b_reg_kostroma],
    [b_reg_kursk],
    [b_reg_lipetsk],
    [b_reg_msk_act],
    [b_reg_msk_inf],
    [b_reg_orel],
    [b_reg_ryazan],
    [b_reg_smolensk],
    [b_reg_tambov],
    [b_reg_tver],
    [b_reg_tula],
    [b_reg_yaroslavl],
    [b_reg_central_reg_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]


# Settings - Yuzhniy Fed Dist - Regions
b_reg_adygeya = 'Адыгея'
b_reg_astrahan = 'Астраханская обл.'
b_reg_volgograd = 'Волгоградская обл.'
b_reg_krasnodar = 'Краснодарский край'
b_reg_krym = 'Крым'
b_reg_rostov = 'Ростовская обл.'
b_reg_yuzhniy_reg_other = 'Прочие поиски по ЮФО'
keyboard_yuzhniy_reg_choice = [
    [b_reg_adygeya],
    [b_reg_astrahan],
    [b_reg_volgograd],
    [b_reg_krasnodar],
    [b_reg_krym],
    [b_reg_rostov],
    [b_reg_yuzhniy_reg_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]


# Settings - Federal Districts
b_fed_dist_dal_vos = 'Дальневосточный ФО'
b_fed_dist_privolz = 'Приволжский ФО'
b_fed_dist_sev_kaz = 'Северо-Кавказский ФО'
b_fed_dist_sev_zap = 'Северо-Западный ФО'
b_fed_dist_sibiria = 'Сибирский ФО'
b_fed_dist_uralsky = 'Уральский ФО'
b_fed_dist_central = 'Центральный ФО'
b_fed_dist_yuzhniy = 'Южный ФО'
b_fed_dist_other_r = 'Прочие поиски по РФ'

keyboard_fed_dist_set = [  # import
    [b_fed_dist_dal_vos],
    [b_fed_dist_privolz],
    [b_fed_dist_sev_kaz],
    [b_fed_dist_sev_zap],
    [b_fed_dist_sibiria],
    [b_fed_dist_uralsky],
    [b_fed_dist_central],
    [b_fed_dist_yuzhniy],
    [b_fed_dist_other_r],
    [b_back_to_start],
]


dict_of_fed_dist = {  # import
    b_fed_dist_dal_vos: keyboard_dal_vost_reg_choice,
    b_fed_dist_privolz: keyboard_privolz_reg_choice,
    b_fed_dist_sev_kaz: keyboard_sev_kav_reg_choice,
    b_fed_dist_sev_zap: keyboard_sev_zap_reg_choice,
    b_fed_dist_sibiria: keyboard_sibiria_reg_choice,
    b_fed_dist_uralsky: keyboard_urals_reg_choice,
    b_fed_dist_central: keyboard_central_reg_choice,
    b_fed_dist_yuzhniy: keyboard_yuzhniy_reg_choice,
}

full_list_of_regions = (
    keyboard_dal_vost_reg_choice[:-1]
    + keyboard_privolz_reg_choice[:-1]
    + keyboard_sev_kav_reg_choice[:-1]
    + keyboard_sev_zap_reg_choice[:-1]
    + keyboard_sibiria_reg_choice[:-1]
    + keyboard_urals_reg_choice[:-1]
    + keyboard_central_reg_choice[:-1]
    + keyboard_yuzhniy_reg_choice[:-1]
    + [[b_fed_dist_other_r]]
)  # noqa – for strange pycharm indent warning

full_dict_of_regions = {word[0] for word in full_list_of_regions}


class ExtendedEnum(Enum):
    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))


class Commands(str, ExtendedEnum):
    c_view_act_searches = '/view_act_searches'
    c_view_latest_searches = '/view_latest_searches'
    c_settings = '/settings'
    c_other = '/other'
    c_map = '/map'


class RoleChoice(str, ExtendedEnum):
    b_role_iam_la = 'я состою в ЛизаАлерт'
    b_role_want_to_be_la = 'я хочу помогать ЛизаАлерт'
    b_role_looking_for_person = 'я ищу человека'
    b_role_other = 'у меня другая задача'
    b_role_secret = 'не хочу говорить'


# TODO ^^^


class UrgencySettings(str, ExtendedEnum):
    b_pref_urgency_highest = 'самым первым (<2 минуты)'
    b_pref_urgency_high = 'пораньше (<5 минут)'
    b_pref_urgency_medium = 'могу ждать (<10 минут)'
    b_pref_urgency_low = 'не сильно важно (>10 минут)'


class MainSettingsMenu(str, ExtendedEnum):
    # Settings menu
    b_set_pref_notif_type = 'настроить виды уведомлений'
    b_set_pref_coords = 'настроить "домашние координаты"'
    b_set_pref_radius = 'настроить максимальный радиус'
    b_set_pref_age = 'настроить возрастные группы БВП'
    b_set_pref_urgency = 'настроить скорость уведомлений'  # <-- TODO: likely to be removed as redundant
    b_set_pref_role = 'настроить вашу роль'  # <-- TODO # noqa
    b_set_forum_nick = 'связать аккаунты бота и форума'
    b_change_forum_nick = 'изменить аккаунт форума'  # noqa
    b_set_topic_type = 'настроить вид поисков'


class NotificationSettingsMenu(str, ExtendedEnum):
    # Settings - notifications
    b_act_all = 'включить: все уведомления'
    b_act_new_search = 'включить: о новых поисках'
    b_act_stat_change = 'включить: об изменениях статусов'
    b_act_all_comments = 'включить: о всех новых комментариях'
    b_act_inforg_com = 'включить: о комментариях Инфорга'
    b_act_field_trips_new = 'включить: о новых выездах'
    b_act_field_trips_change = 'включить: об изменениях в выездах'
    b_act_coords_change = 'включить: о смене места штаба'
    b_act_first_post_change = 'включить: об изменениях в первом посте'
    b_deact_all = 'настроить более гибко'
    b_deact_new_search = 'отключить: о новых поисках'
    b_deact_stat_change = 'отключить: об изменениях статусов'
    b_deact_all_comments = 'отключить: о всех новых комментариях'
    b_deact_inforg_com = 'отключить: о комментариях Инфорга'
    b_deact_field_trips_new = 'отключить: о новых выездах'
    b_deact_field_trips_change = 'отключить: об изменениях в выездах'
    b_deact_coords_change = 'отключить: о смене места штаба'
    b_deact_first_post_change = 'отключить: об изменениях в первом посте'


class AgePreferencesMenu(str, ExtendedEnum):
    b_pref_age_0_6_act = 'отключить: Маленькие Дети 0-6 лет'
    b_pref_age_0_6_deact = 'включить: Маленькие Дети 0-6 лет'
    b_pref_age_7_13_act = 'отключить: Подростки 7-13 лет'
    b_pref_age_7_13_deact = 'включить: Подростки 7-13 лет'
    b_pref_age_14_20_act = 'отключить: Молодежь 14-20 лет'
    b_pref_age_14_20_deact = 'включить: Молодежь 14-20 лет'
    b_pref_age_21_50_act = 'отключить: Взрослые 21-50 лет'
    b_pref_age_21_50_deact = 'включить: Взрослые 21-50 лет'
    b_pref_age_51_80_act = 'отключить: Старшее Поколение 51-80 лет'
    b_pref_age_51_80_deact = 'включить: Старшее Поколение 51-80 лет'
    b_pref_age_81_on_act = 'отключить: Старцы более 80 лет'
    b_pref_age_81_on_deact = 'включить: Старцы более 80 лет'


class MainMenu(str, ExtendedEnum):
    b_view_act_searches = 'посмотреть актуальные поиски'
    b_settings = 'настроить бот'
    b_other = 'другие возможности'
    b_map = '🔥Карта Поисков 🔥'


class DistanceSettings(str, ExtendedEnum):
    b_pref_radius_act = 'включить ограничение по расстоянию'
    b_pref_radius_deact = 'отключить ограничение по расстоянию'
    b_pref_radius_change = 'изменить ограничение по расстоянию'


# Other menu
class OtherMenu(str, ExtendedEnum):
    b_view_latest_searches = 'посмотреть последние поиски'
    b_goto_community = 'написать разработчику бота'
    b_goto_first_search = 'ознакомиться с информацией для новичка'
    b_goto_photos = 'посмотреть красивые фото с поисков'


# Admin - specially keep it for Admin, regular users unlikely will be interested in it

b_act_titles = 'названия'  # these are "Title update notification" button
