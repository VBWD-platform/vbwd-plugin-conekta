"""Plugin tests — MXN-only + method allow-list."""
from decimal import Decimal
from uuid import uuid4

from vbwd.plugins.base import PluginStatus

from plugins.conekta import ConektaPlugin, DEFAULT_CONFIG, SUPPORTED_METHODS


class TestConektaPlugin:
    def test_metadata(self):
        assert ConektaPlugin().metadata.name == "conekta"

    def test_initialize_merges(self):
        plugin = ConektaPlugin()
        plugin.initialize({"test_public_key": "pk_x"})
        assert plugin.status == PluginStatus.INITIALIZED
        assert plugin._config["test_public_key"] == "pk_x"
        assert plugin._config["api_version"] == DEFAULT_CONFIG["api_version"]

    def test_rejects_non_mxn(self):
        plugin = ConektaPlugin()
        plugin.initialize({})
        result = plugin.create_payment_intent(
            amount=Decimal("100"),
            currency="USD",
            subscription_id=uuid4(),
            user_id=uuid4(),
            metadata={"method": "card"},
        )
        assert result.success is False
        assert "MXN" in (result.error_message or "")

    def test_rejects_unsupported_method(self):
        plugin = ConektaPlugin()
        plugin.initialize({})
        result = plugin.create_payment_intent(
            amount=Decimal("100"),
            currency="MXN",
            subscription_id=uuid4(),
            user_id=uuid4(),
            metadata={"method": "bitcoin"},
        )
        assert result.success is False
        assert "method must be one of" in (result.error_message or "")

    def test_supported_methods_include_card_oxxo_spei(self):
        assert set(SUPPORTED_METHODS) == {"card", "oxxo_cash", "spei"}
