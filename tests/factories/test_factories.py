import pytest

from tests.factories.db_factories import DictNotifTypeFactory, NotifByUserFactory


@pytest.mark.skip(reason='helper for factories tuning')
class TestCreateModel:
    def test_create_notif_by_user(self):
        model = NotifByUserFactory.create_sync()
        assert model

    def test_create_dict_notif_type(self):
        DictNotifTypeFactory.build()
        model = DictNotifTypeFactory.create_sync()
        assert model
