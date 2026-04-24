"""Idempotent demo data for Conekta."""
from decimal import Decimal

from vbwd.extensions import db

from plugins.conekta.conekta.models import ConektaOrder


def populate_db() -> None:
    existing = (
        db.session.query(ConektaOrder)
        .filter_by(invoice_no="DEMO-CK-0001")
        .one_or_none()
    )
    if existing is not None:
        return
    db.session.add(
        ConektaOrder(
            invoice_no="DEMO-CK-0001",
            order_id="ord_demo_1",
            method="oxxo_cash",
            amount=Decimal("500.00"),
            currency="MXN",
            reference="12345612345612",
            status="completed",
            last_provider_status="paid",
            extra_data={"demo": True},
        )
    )
    db.session.commit()


if __name__ == "__main__":
    populate_db()
