"""Conekta services — domain mapping + webhook handling."""
from decimal import Decimal
from typing import Any, Dict, Optional

from vbwd.extensions import db

from plugins.conekta.conekta.models import ConektaOrder


STATUS_MAP = {
    "paid": "completed",
    "pending_payment": "pending",
    "processing": "processing",
    "expired": "expired",
    "cancelled": "cancelled",
    "refunded": "refunded",
    "declined": "failed",
}


def map_conekta_status(provider_status: str) -> str:
    if not provider_status:
        return "failed"
    return STATUS_MAP.get(provider_status.lower(), "failed")


class ConektaService:
    def __init__(self, session=None):
        self._session = session or db.session

    def record_order_created(
        self,
        invoice_no: str,
        order_id: str,
        method: str,
        amount: Decimal,
        currency: str,
        msi: Optional[int] = None,
        reference: Optional[str] = None,
        clabe: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> ConektaOrder:
        order = self._get_or_create(invoice_no)
        order.order_id = order_id
        order.method = method
        order.amount = amount
        order.currency = currency
        order.msi = msi
        order.reference = reference
        order.clabe = clabe
        order.status = "pending"
        order.extra_data = extra_data
        self._session.add(order)
        self._session.commit()
        return order

    def apply_provider_update(
        self, invoice_no: str, provider_payload: Dict[str, Any]
    ) -> ConektaOrder:
        order = self._get_or_create(invoice_no)
        provider_status = provider_payload.get("payment_status") or provider_payload.get(
            "status", ""
        )
        new_status = map_conekta_status(provider_status)
        if (
            order.status == new_status
            and order.last_provider_status == provider_status
        ):
            return order
        order.status = new_status
        order.last_provider_status = provider_status
        self._session.commit()
        return order

    def _get_or_create(self, invoice_no: str) -> ConektaOrder:
        order = (
            self._session.query(ConektaOrder)
            .filter_by(invoice_no=invoice_no)
            .one_or_none()
        )
        if order is None:
            order = ConektaOrder(
                invoice_no=invoice_no,
                method="card",
                amount=Decimal("0"),
                currency="MXN",
            )
        return order


class ConektaWebhookHandler:
    def __init__(self, service: Optional[ConektaService] = None):
        self._service = service or ConektaService()

    def handle(self, payload: Dict[str, Any]) -> ConektaOrder:
        """Conekta webhook payload: `data.object` carries the order."""
        data = payload.get("data", {})
        order_obj = data.get("object", payload)
        invoice_no = (
            order_obj.get("metadata", {}).get("invoice_no")
            if isinstance(order_obj.get("metadata"), dict)
            else None
        )
        if not invoice_no:
            raise ValueError(
                "missing metadata.invoice_no in Conekta webhook"
            )
        return self._service.apply_provider_update(invoice_no, order_obj)
