from dataclasses import dataclass
from typing import Any


@dataclass
class SearchSummary:
    topic_type: Any = None
    topic_id: Any = None
    parsed_time: Any = None
    status: Any = None
    title: Any = None
    link: Any = None
    start_time: Any = None
    num_of_replies: Any = None
    name: Any = None
    display_name: Any = None
    age: Any = None
    searches_table_id: Any = None
    folder_id: Any = None
    age_max: Any = None
    age_min: Any = None
    num_of_persons: Any = None
    city_locations: Any = None  # city / town / place – approximate coordinates
    hq_locations: Any = None  # shtab –exact coordinates
    new_status: Any = None
    full_dict: Any = None

    def __str__(self):
        return (
            f'{self.parsed_time} – {self.folder_id} / {self.topic_id} : {self.name} - {self.age} – '
            f'{self.num_of_replies}. NEW: {self.display_name} – {self.age_min} – {self.age_max} – '
            f'{self.num_of_persons}'
        )
