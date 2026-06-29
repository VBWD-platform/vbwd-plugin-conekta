"""Conekta plugin — Mexico direct: cards + MSI + OXXO + SPEI."""
from typing import Optional, Dict, Any, TYPE_CHECKING
from decimal import Decimal
from uuid import UUID

from vbwd.plugins.base import PluginMetadata
from vbwd.plugins.payment_provider import (
    PaymentProviderPlugin,
    PaymentResult,
    PaymentStatus,
)

if TYPE_CHECKING:
    from flask import Blueprint


SUPPORTED_METHODS = ("card", "oxxo_cash", "spei")
MSI_ELIGIBLE_BRANDS = ("visa", "mastercard", "amex")
DEFAULT_MSI_PLANS = (3, 6, 9, 12)


DEFAULT_CONFIG = {
    "sandbox": True,
    "test_public_key": "",
    "test_private_key": "",
    "test_api_url": "https://api.conekta.io",
    "live_public_key": "",
    "live_private_key": "",
    "live_api_url": "https://api.conekta.io",
    "api_version": "2.2.0",
    "enabled_methods": list(SUPPORTED_METHODS),
    "msi_enabled": True,
    "msi_plans": list(DEFAULT_MSI_PLANS),
    "oxxo_expiry_days": 3,
    "spei_expiry_days": 1,
    "currency": "MXN",
}


class ConektaPlugin(PaymentProviderPlugin):
    """Conekta — Mexican PSP with best-in-class MSI + OXXO + SPEI."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="conekta",
            version="26.6",
            author="VBWD Team",
            description=(
                "Conekta (Mexico) — cards with MSI, OXXO cash vouchers, "
                "SPEI bank transfer. MXN-only."
            ),
            dependencies=[],
        )

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        merged = {**DEFAULT_CONFIG}
        if config:
            merged.update(config)
        super().initialize(merged)

    def get_blueprint(self) -> Optional["Blueprint"]:
        from plugins.conekta.conekta.routes import conekta_plugin_bp

        return conekta_plugin_bp

    def get_url_prefix(self) -> Optional[str]:
        return "/api/v1/plugins/conekta"

    @property
    def admin_permissions(self):
        return [
            {
                "key": "payments.configure",
                "label": "Payment provider settings",
                "group": "Payments",
            },
        ]

    def on_enable(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    def _get_adapter(self):
        from flask import current_app
        from plugins.conekta.conekta.sdk_adapter import ConektaSDKAdapter
        from vbwd.sdk.interface import SDKConfig

        config_store = current_app.config_store
        config = config_store.get_config("conekta")
        prefix = "test_" if config.get("sandbox", True) else "live_"
        return ConektaSDKAdapter(
            SDKConfig(
                api_key=config.get(f"{prefix}private_key", ""),
                sandbox=config.get("sandbox", True),
            ),
            public_key=config.get(f"{prefix}public_key", ""),
            api_url=config.get(f"{prefix}api_url", DEFAULT_CONFIG[f"{prefix}api_url"]),
            api_version=config.get("api_version", DEFAULT_CONFIG["api_version"]),
        )

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        subscription_id: UUID,
        user_id: UUID,
        metadata: Optional[Dict[str, Any]] = None,
        capture: bool = True,
    ) -> PaymentResult:
        if currency.upper() != "MXN":
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error_message=f"Conekta supports MXN only, got {currency}",
            )
        metadata = metadata or {}
        method = metadata.get("method", "card").lower()
        if method not in SUPPORTED_METHODS:
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error_message=(
                    f"method must be one of {SUPPORTED_METHODS}; got {method!r}"
                ),
            )

        adapter = self._get_adapter()
        response = adapter.create_order(
            amount=amount,
            currency=currency,
            invoice_no=str(subscription_id),
            customer_email=metadata.get("customer_email", ""),
            customer_name=metadata.get("customer_name", "Customer"),
            method=method,
            token_id=metadata.get("token_id"),
            msi=metadata.get("msi"),
        )
        if not response.success:
            return PaymentResult(
                success=False,
                error_message=response.error,
                status=PaymentStatus.FAILED,
            )
        return PaymentResult(
            success=True,
            transaction_id=response.data.get("id"),
            status=PaymentStatus.PENDING,
            metadata=response.data,
        )

    def capture_payment(
        self, payment_id: str, amount: Optional[Decimal] = None
    ) -> PaymentResult:
        adapter = self._get_adapter()
        response = adapter.get_order(payment_id)
        if not response.success:
            return PaymentResult(
                success=False,
                error_message=response.error,
                status=PaymentStatus.FAILED,
            )
        status = _map_conekta_status(response.data.get("payment_status", ""))
        return PaymentResult(
            success=status == PaymentStatus.COMPLETED,
            transaction_id=payment_id,
            status=status,
        )

    def release_authorization(self, payment_id: str) -> PaymentResult:
        return PaymentResult(
            success=False,
            status=PaymentStatus.FAILED,
            error_message=(
                "Conekta does not expose authorization release via the " "Orders API"
            ),
        )

    def process_payment(
        self, payment_intent_id: str, payment_method: str
    ) -> PaymentResult:
        return self.capture_payment(payment_intent_id)

    def refund_payment(
        self, transaction_id: str, amount: Optional[Decimal] = None
    ) -> PaymentResult:
        adapter = self._get_adapter()
        response = adapter.refund_order(order_id=transaction_id, amount=amount)
        if not response.success:
            return PaymentResult(
                success=False,
                error_message=response.error,
                status=PaymentStatus.FAILED,
            )
        return PaymentResult(
            success=True,
            transaction_id=transaction_id,
            status=PaymentStatus.REFUNDED,
        )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        adapter = self._get_adapter()
        return adapter.verify_webhook(payload, signature)

    def handle_webhook(self, payload: Dict[str, Any]) -> None:
        from plugins.conekta.conekta.services import ConektaWebhookHandler

        ConektaWebhookHandler().handle(payload)


def _map_conekta_status(status: str) -> PaymentStatus:
    mapping = {
        "paid": PaymentStatus.COMPLETED,
        "pending_payment": PaymentStatus.PENDING,
        "processing": PaymentStatus.PROCESSING,
        "expired": PaymentStatus.FAILED,
        "cancelled": PaymentStatus.CANCELLED,
        "refunded": PaymentStatus.REFUNDED,
        "declined": PaymentStatus.FAILED,
    }
    return mapping.get(status.lower(), PaymentStatus.FAILED)
