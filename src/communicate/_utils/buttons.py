import hashlib
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
