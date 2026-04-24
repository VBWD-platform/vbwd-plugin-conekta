"""Unit tests for ConektaService + webhook handler."""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from plugins.conekta.conekta.services import (
    ConektaService,
    ConektaWebhookHandler,
    map_conekta_status,
)


class TestStatusMap:
    @pytest.mark.parametrize(
        "provider,expected",
        [
            ("paid", "completed"),
            ("pending_payment", "pending"),
            ("processing", "processing"),
            ("expired", "expired"),
            ("cancelled", "cancelled"),
            ("refunded", "refunded"),
            ("declined", "failed"),
            ("", "failed"),
            ("??", "failed"),
        ],
    )
    def test_maps(self, provider, expected):
        assert map_conekta_status(provider) == expected


class TestConektaService:
    def test_record_order_created(self):
        session = MagicMock()
        session.query.return_value.filter_by.return_value.one_or_none.return_value = (
            None
        )
        svc = ConektaService(session=session)

        order = svc.record_order_created(
            invoice_no="INV-1",
            order_id="ord_1",
            method="oxxo_cash",
            amount=Decimal("500"),
            currency="MXN",
            reference="12345612345612",
        )
        assert order.order_id == "ord_1"
        assert order.reference == "12345612345612"
        assert order.status == "pending"
        session.commit.assert_called_once()

    def test_apply_provider_update_idempotent(self):
        existing = MagicMock()
        existing.status = "completed"
        existing.last_provider_status = "paid"
        session = MagicMock()
        session.query.return_value.filter_by.return_value.one_or_none.return_value = (
            existing
        )
        svc = ConektaService(session=session)

        svc.apply_provider_update("INV-1", {"payment_status": "paid"})
        session.commit.assert_not_called()


class TestWebhookHandler:
    def test_rejects_missing_invoice_metadata(self):
        handler = ConektaWebhookHandler(service=MagicMock())
        with pytest.raises(ValueError, match="invoice_no"):
            handler.handle({"data": {"object": {"payment_status": "paid"}}})

    def test_reads_metadata_invoice_no(self):
        svc = MagicMock()
        ConektaWebhookHandler(service=svc).handle(
            {
                "type": "order.paid",
                "data": {
                    "object": {
                        "payment_status": "paid",
                        "metadata": {"invoice_no": "INV-1"},
                    }
                },
            }
        )
        svc.apply_provider_update.assert_called_once()
        assert svc.apply_provider_update.call_args[0][0] == "INV-1"
