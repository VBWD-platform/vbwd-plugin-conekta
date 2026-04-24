# Conekta Plugin (Backend)

Mexican PSP — cards with MSI (meses sin intereses) + OXXO cash
vouchers + SPEI bank transfer. MXN-only.

## API Routes

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/plugins/conekta/orders` | Bearer | Create order (card/oxxo_cash/spei) |
| GET | `/api/v1/plugins/conekta/orders/:invoice/status` | Bearer | Refresh status |
| POST | `/api/v1/plugins/conekta/webhooks` | Digest HMAC | Webhook receiver |
| POST | `/api/v1/plugins/conekta/orders/:invoice/refund` | Admin | Refund (full/partial) |

## Database

`conekta_orders` — one row per invoice; stores OXXO reference +
SPEI CLABE + expiry + MSI count + Conekta-side status.

## Frontend bundles

- User: [`vbwd-fe-user-plugin-conekta-payment`](https://github.com/VBWD-platform/vbwd-fe-user-plugin-conekta-payment)
- Admin: [`vbwd-fe-admin-plugin-conekta-admin`](https://github.com/VBWD-platform/vbwd-fe-admin-plugin-conekta-admin)

---

**Core:** [vbwd-backend](https://github.com/VBWD-platform/vbwd-backend)
