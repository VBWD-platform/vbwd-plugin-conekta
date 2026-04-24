"""Unit tests for ConektaSDKAdapter (TDD-first)."""
import base64
from decimal import Decimal
from unittest.mock import MagicMock

from plugins.conekta.conekta.sdk_adapter import compute_msi_plans


class TestHeaders:
    def test_basic_auth_private_key_colon(self, adapter):
        headers = adapter._headers()
        token = headers["Authorization"].split(" ")[1]
        assert base64.b64decode(token).decode() == "key_test_private_abc:"

    def test_accept_pins_api_version(self, adapter):
        assert adapter._headers()["Accept"] == "application/vnd.conekta-v2.2.0+json"


class TestCreateOrderCard:
    def test_card_requires_token(self, adapter):
        resp = adapter.create_order(
            amount=Decimal("100"),
            currency="MXN",
            invoice_no="INV-1",
            customer_email="a@b.com",
            customer_name="A",
            method="card",
            token_id=None,
        )
        assert resp.success is False
        assert "token_id" in (resp.error or "")

    def test_card_with_msi_propagates(self, adapter, mocker):
        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["json"] = json
            fake = MagicMock()
            fake.status_code = 200
            fake.json.return_value = {"id": "ord_1"}
            return fake

        mocker.patch(
            "plugins.conekta.conekta.sdk_adapter.requests.post",
            side_effect=_fake_post,
        )
        adapter.create_order(
            amount=Decimal("1200"),
            currency="MXN",
            invoice_no="INV-1",
            customer_email="a@b.com",
            customer_name="A",
            method="card",
            token_id="tok_123",
            msi=6,
        )
        charge = captured["json"]["charges"][0]
        assert charge["payment_method"]["monthly_installments"] == 6
        assert charge["payment_method"]["token_id"] == "tok_123"

    def test_amount_sent_as_cents(self, adapter, mocker):
        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["json"] = json
            fake = MagicMock()
            fake.status_code = 200
            fake.json.return_value = {"id": "ord_1"}
            return fake

        mocker.patch(
            "plugins.conekta.conekta.sdk_adapter.requests.post",
            side_effect=_fake_post,
        )
        adapter.create_order(
            amount=Decimal("99.50"),
            currency="MXN",
            invoice_no="INV-1",
            customer_email="a@b.com",
            customer_name="A",
            method="card",
            token_id="tok_x",
        )
        assert captured["json"]["charges"][0]["amount"] == 9950


class TestCreateOrderOxxo:
    def test_oxxo_cash_has_no_token(self, adapter, mocker):
        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["json"] = json
            fake = MagicMock()
            fake.status_code = 200
            fake.json.return_value = {
                "id": "ord_oxxo",
                "charges": {
                    "data": [
                        {
                            "payment_method": {
                                "type": "oxxo_cash",
                                "reference": "12345612345612",
                                "expires_at": 1715000000,
                            }
                        }
                    ]
                },
            }
            return fake

        mocker.patch(
            "plugins.conekta.conekta.sdk_adapter.requests.post",
            side_effect=_fake_post,
        )
        resp = adapter.create_order(
            amount=Decimal("500"),
            currency="MXN",
            invoice_no="INV-1",
            customer_email="a@b.com",
            customer_name="A",
            method="oxxo_cash",
        )
        assert resp.success is True
        assert captured["json"]["charges"][0]["payment_method"]["type"] == "oxxo_cash"
        assert "token_id" not in captured["json"]["charges"][0]["payment_method"]


class TestRefund:
    def test_amount_sent_as_cents(self, adapter, mocker):
        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["json"] = json
            fake = MagicMock()
            fake.status_code = 200
            fake.json.return_value = {"refunded": True}
            return fake

        mocker.patch(
            "plugins.conekta.conekta.sdk_adapter.requests.post",
            side_effect=_fake_post,
        )
        adapter.refund_order("ord_x", amount=Decimal("25.00"))
        assert captured["json"]["amount"] == 2500

    def test_full_refund_omits_amount(self, adapter, mocker):
        captured = {}

        def _fake_post(url, json, headers, timeout):
            captured["json"] = json
            fake = MagicMock()
            fake.status_code = 200
            fake.json.return_value = {"refunded": True}
            return fake

        mocker.patch(
            "plugins.conekta.conekta.sdk_adapter.requests.post",
            side_effect=_fake_post,
        )
        adapter.refund_order("ord_x")
        assert "amount" not in captured["json"]


class TestWebhookVerify:
    def test_accepts_valid(self, adapter):
        import hashlib
        import hmac

        body = b'{"type":"order.paid"}'
        sig = base64.b64encode(
            hmac.new(b"key_test_private_abc", body, hashlib.sha256).digest()
        ).decode()
        assert adapter.verify_webhook(body, sig) is True

    def test_rejects_wrong(self, adapter):
        assert adapter.verify_webhook(b"body", "deadbeef") is False

    def test_rejects_empty(self, adapter):
        assert adapter.verify_webhook(b"body", "") is False


class TestErrorParse:
    def test_4xx_extracts_details_message(self, adapter, mocker):
        fake = MagicMock()
        fake.status_code = 422
        fake.json.return_value = {
            "details": [{"message": "token_id is required"}],
            "message": "Validation error",
        }
        mocker.patch(
            "plugins.conekta.conekta.sdk_adapter.requests.post",
            return_value=fake,
        )
        resp = adapter.create_order(
            amount=Decimal("1"),
            currency="MXN",
            invoice_no="INV-1",
            customer_email="a@b.com",
            customer_name="A",
            method="card",
            token_id="tok",
        )
        assert resp.success is False
        assert "token_id is required" in (resp.error or "")


class TestComputeMsiPlans:
    def test_unsupported_brand_single_pay(self):
        assert compute_msi_plans(Decimal("1000"), "carnet") == [1]

    def test_amount_under_300_single_pay(self):
        assert compute_msi_plans(Decimal("299"), "visa") == [1]

    def test_eligible_returns_plans(self):
        plans = compute_msi_plans(Decimal("1000"), "mastercard")
        assert plans == [1, 3, 6, 9, 12]

    def test_custom_plans(self):
        plans = compute_msi_plans(Decimal("1000"), "visa", plans=[3, 6])
        assert plans == [1, 3, 6]
