"""Conekta plugin API routes."""
import logging
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, request

from vbwd.middleware.auth import require_auth

from plugins.conekta.conekta.services import (
    ConektaService,
    ConektaWebhookHandler,
)

logger = logging.getLogger(__name__)

conekta_plugin_bp = Blueprint("conekta_plugin", __name__)


def _get_plugin():
    manager = current_app.plugin_manager
    plugin = manager.get_plugin("conekta")
    if plugin is None:
        raise RuntimeError("conekta plugin not enabled")
    return plugin


@conekta_plugin_bp.route("/orders", methods=["POST"])
@require_auth
def create_order():
    body = request.get_json(silent=True) or {}
    required = ("invoice_no", "amount", "method", "customer_email")
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": "missing fields", "fields": missing}), 400

    try:
        amount = Decimal(str(body["amount"]))
    except (ValueError, ArithmeticError):
        return jsonify({"error": "invalid amount"}), 400

    plugin = _get_plugin()
    adapter = plugin._get_adapter()
    response = adapter.create_order(
        amount=amount,
        currency=body.get("currency", "MXN"),
        invoice_no=body["invoice_no"],
        customer_email=body["customer_email"],
        customer_name=body.get("customer_name", "Customer"),
        method=body["method"],
        token_id=body.get("token_id"),
        msi=body.get("msi"),
    )
    if not response.success:
        return jsonify({"error": response.error or "Conekta error"}), 502

    data = response.data
    charges = data.get("charges", {}).get("data", [])
    charge = charges[0] if charges else {}
    payment_method = charge.get("payment_method", {})
    reference = payment_method.get("reference")
    clabe = payment_method.get("clabe")
    expires_at_ts = payment_method.get("expires_at")

    from datetime import datetime, timezone

    expires_dt = None
    if expires_at_ts:
        try:
            expires_dt = datetime.fromtimestamp(
                int(expires_at_ts), tz=timezone.utc
            )
        except (TypeError, ValueError):
            expires_dt = None

    service = ConektaService()
    order = service.record_order_created(
        invoice_no=body["invoice_no"],
        order_id=data.get("id", ""),
        method=body["method"],
        amount=amount,
        currency=body.get("currency", "MXN"),
        msi=body.get("msi"),
        reference=reference,
        clabe=clabe,
        extra_data=data,
    )
    if expires_dt is not None:
        order.expires_at = expires_dt
        service._session.commit()

    return jsonify(order.to_dict()), 201


@conekta_plugin_bp.route("/orders/<invoice_no>/status", methods=["GET"])
@require_auth
def get_status(invoice_no: str):
    from vbwd.extensions import db

    from plugins.conekta.conekta.models import ConektaOrder

    order = (
        db.session.query(ConektaOrder).filter_by(invoice_no=invoice_no).one_or_none()
    )
    if order is None:
        return jsonify({"error": "not found"}), 404
    if not order.order_id:
        return jsonify(order.to_dict()), 200

    plugin = _get_plugin()
    response = plugin._get_adapter().get_order(order.order_id)
    if response.success:
        ConektaService().apply_provider_update(invoice_no, response.data)
    return jsonify(order.to_dict()), 200


@conekta_plugin_bp.route("/webhooks", methods=["POST"])
def webhook():
    signature = request.headers.get("Digest", "")
    plugin = _get_plugin()
    adapter = plugin._get_adapter()
    if not adapter.verify_webhook(request.get_data(), signature):
        return jsonify({"error": "invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    try:
        ConektaWebhookHandler().handle(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return "", 204


@conekta_plugin_bp.route("/orders/<invoice_no>/refund", methods=["POST"])
@require_auth
def refund(invoice_no: str):
    from vbwd.extensions import db

    from plugins.conekta.conekta.models import ConektaOrder

    order = (
        db.session.query(ConektaOrder).filter_by(invoice_no=invoice_no).one_or_none()
    )
    if order is None or not order.order_id:
        return jsonify({"error": "not found"}), 404

    body = request.get_json(silent=True) or {}
    amount = body.get("amount")
    if amount is not None:
        try:
            amount = Decimal(str(amount))
        except (ValueError, ArithmeticError):
            return jsonify({"error": "invalid amount"}), 400

    plugin = _get_plugin()
    response = plugin._get_adapter().refund_order(order.order_id, amount)
    if not response.success:
        return jsonify({"error": response.error or "Conekta error"}), 502
    return jsonify({"order_id": order.order_id}), 200
