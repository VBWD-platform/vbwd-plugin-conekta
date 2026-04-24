"""Conekta SDK adapter — Basic-auth with private key + pinned API version."""
import base64
import hashlib
import hmac
from decimal import Decimal
from typing import Any, Dict, Optional

import requests

from vbwd.sdk.base import BaseSDKAdapter
from vbwd.sdk.interface import SDKConfig, SDKResponse


MSI_ELIGIBLE_BRANDS = ("visa", "mastercard", "amex")
DEFAULT_MSI_PLANS = (3, 6, 9, 12)


def compute_msi_plans(
    amount: Decimal,
    card_brand: Optional[str],
    plans: Optional[list] = None,
) -> list:
    """Return eligible MSI counts for a card brand + amount.

    MSI eligibility is bin-dependent at Conekta; this is the baseline
    rule. Real tables refine per-bank; see config `msi_plans`.
    """
    plans = plans if plans is not None else list(DEFAULT_MSI_PLANS)
    if not card_brand or card_brand.lower() not in MSI_ELIGIBLE_BRANDS:
        return [1]
    if amount < Decimal("300"):
        return [1]
    return [1] + plans


class ConektaSDKAdapter(BaseSDKAdapter):
    """Conekta Orders API adapter."""

    def __init__(
        self,
        config: SDKConfig,
        public_key: str,
        api_url: str,
        api_version: str = "2.2.0",
        idempotency_service=None,
    ):
        super().__init__(config, idempotency_service)
        self._private_key = config.api_key
        self._public_key = public_key
        self._api_url = api_url.rstrip("/")
        self._api_version = api_version

    @property
    def provider_name(self) -> str:
        return "conekta"

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> SDKResponse:
        return self.create_order(
            amount=amount,
            currency=currency,
            invoice_no=metadata.get("invoice_no", ""),
            customer_email=metadata.get("customer_email", ""),
            customer_name=metadata.get("customer_name", "Customer"),
            method=metadata.get("method", "card"),
            token_id=metadata.get("token_id"),
            msi=metadata.get("msi"),
        )

    def capture_payment(
        self,
        payment_intent_id: str,
        idempotency_key: Optional[str] = None,
    ) -> SDKResponse:
        return self.get_order(payment_intent_id)

    def release_authorization(self, payment_intent_id: str) -> SDKResponse:
        return SDKResponse(
            success=False,
            error="Conekta does not expose authorization release",
        )

    def get_payment_status(self, payment_intent_id: str) -> SDKResponse:
        return self.get_order(payment_intent_id)

    def refund_payment(
        self,
        payment_intent_id: str,
        amount: Optional[Decimal] = None,
        idempotency_key: Optional[str] = None,
    ) -> SDKResponse:
        return self.refund_order(payment_intent_id, amount)

    def create_order(
        self,
        amount: Decimal,
        currency: str,
        invoice_no: str,
        customer_email: str,
        customer_name: str,
        method: str,
        token_id: Optional[str] = None,
        msi: Optional[int] = None,
    ) -> SDKResponse:
        """Create a Conekta Order.

        method: 'card' | 'oxxo_cash' | 'spei'
        For 'card' pass token_id (from Conekta.js).
        """
        charge: Dict[str, Any] = {"amount": _to_cents(amount)}
        if method == "card":
            if not token_id:
                return SDKResponse(success=False, error="card method requires token_id")
            charge["payment_method"] = {"type": "default", "token_id": token_id}
            if msi and msi > 1:
                charge["payment_method"]["monthly_installments"] = msi
        elif method == "oxxo_cash":
            charge["payment_method"] = {"type": "oxxo_cash"}
        elif method == "spei":
            charge["payment_method"] = {"type": "spei"}

        body = {
            "line_items": [
                {
                    "name": f"Invoice {invoice_no}",
                    "unit_price": _to_cents(amount),
                    "quantity": 1,
                }
            ],
            "currency": currency,
            "customer_info": {
                "name": customer_name,
                "email": customer_email,
            },
            "charges": [charge],
            "metadata": {"invoice_no": invoice_no},
        }
        return self._post("/orders", body)

    def get_order(self, order_id: str) -> SDKResponse:
        return self._get(f"/orders/{order_id}")

    def refund_order(
        self, order_id: str, amount: Optional[Decimal] = None
    ) -> SDKResponse:
        payload: Dict[str, Any] = {"reason": "requested_by_client"}
        if amount is not None:
            payload["amount"] = _to_cents(amount)
        return self._post(f"/orders/{order_id}/refunds", payload)

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify Conekta webhook `Digest` header (HMAC-SHA256, base64)."""
        if not signature:
            return False
        expected = base64.b64encode(
            hmac.new(self._private_key.encode(), payload, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(expected, signature)

    # ── internal helpers ───────────────────────────────────────────────

    def _post(self, path: str, body: Dict[str, Any]) -> SDKResponse:
        try:
            resp = requests.post(
                f"{self._api_url}{path}",
                json=body,
                headers=self._headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            return SDKResponse(success=False, error=f"network: {exc}")
        return self._parse(resp)

    def _get(self, path: str) -> SDKResponse:
        try:
            resp = requests.get(
                f"{self._api_url}{path}",
                headers=self._headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            return SDKResponse(success=False, error=f"network: {exc}")
        return self._parse(resp)

    def _parse(self, resp: requests.Response) -> SDKResponse:
        if resp.status_code >= 500:
            return SDKResponse(
                success=False,
                error=f"Conekta {resp.status_code}: {resp.text[:200]}",
            )
        try:
            body = resp.json()
        except ValueError:
            return SDKResponse(success=False, error="invalid JSON from Conekta")
        if resp.status_code >= 400:
            details = body.get("details")
            msg = body.get("message", f"HTTP {resp.status_code}")
            if isinstance(details, list) and details:
                msg = details[0].get("message", msg)
            return SDKResponse(success=False, data=body, error=msg)
        return SDKResponse(success=True, data=body)

    def _headers(self) -> Dict[str, str]:
        token = base64.b64encode(f"{self._private_key}:".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Accept": f"application/vnd.conekta-v{self._api_version}+json",
            "Content-Type": "application/json",
        }


def _to_cents(amount: Decimal) -> int:
    """Convert MXN amount to cents (Conekta expects integer cents)."""
    return int((amount * 100).to_integral_value())
