"""Odoo -> GOAT entitlement adapter (see docs/odoo-entitlement-contract.md).

GOAT core is billing-agnostic: it only exposes
``POST /api/v2/webhooks/odoo/entitlement`` and enforces the entitlement state
on the organization row. This task is the adapter in between: it reads a
subscriptions (``sale.order``) from Odoo over XML-RPC, computes the
entitlement per organization, and POSTs it to core.

Entitlement math::

    total_<quota> = sum(line qty x product.x_goat_<quota>)   # base product
                                                             # included: its
                                                             # own line carries
                                                             # the base values
    subscription-level x_goat_<quota> > 0  ->  override wins (negotiated deals)

Premium features: ``sale.order.x_goat_white_label`` checkbox -> ``extras``
grant-list (``["white_label"]`` / ``[]``).

One organization can have several subscriptions (an old cancelled one next to
the active one), so the entitlement is computed per ORGANIZATION: with at
least one active (``3_progress``) subscription only the active ones count and
their quotas add up; without, the most recently changed paused/churned one
suspends the organization. Pushing subscriptions one by one would let a stale
cancelled one overwrite the active one.

Two modes, one task:
  * ``order_id > 0``  — push the whole organization of that subscription
    (live path: Odoo automation rule -> Windmill webhook -> this task).
  * ``order_id == 0`` — reconcile: push every organization that has a
    subscription in a pushable state, once (nightly schedule; heals missed
    webhooks and doubles as the initial backfill).

Required environment (Windmill variables/secrets):
    ODOO_URL, ODOO_DB                            — Plan4Better's Odoo (shared)
    ODOO_BILLING_USER, ODOO_BILLING_API_KEY      — the billing user's XML-RPC
                                                   login (the user goes away
                                                   with JSON-2, see core.odoo)
    CORE_URL                                     — GOAT core base URL
    ODOO_WEBHOOK_SECRET                          — shared secret for core

Windmill path: f/goat/tasks/odoo_entitlement_push
"""

import logging
import os
import xmlrpc.client
from datetime import UTC, datetime
from typing import Any, Self
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = ["OdooEntitlementPushParams", "OdooEntitlementTask", "main"]

# subscription_state values (Odoo 19 sale_subscription) worth pushing.
# Draft/renewal/upsell quotations describe future state; '5_renewed' means a
# newer subscription supersedes this one (that one gets pushed instead).
PUSHABLE_STATES = {"3_progress", "4_paused", "6_churn"}
SUSPENDED_STATES = {"4_paused", "6_churn"}

# payload quota key -> x_goat field name (on products AND on the order)
# Monthly credits: same sum/override rule, but only sent when the catalogue
# grants some (an Odoo without the field, or products without credits, leave
# the organization's allowance as it is instead of setting it to 0).
CREDIT_FIELD = "x_goat_credits"

QUOTA_FIELDS = {
    "total_editors": "x_goat_editors",
    "total_viewers": "x_goat_viewers",
    "total_projects": "x_goat_projects",
    "total_storage": "x_goat_storage_mb",
}

# order-level feature checkboxes -> extras entries. Extend as features are
# added in Odoo (checkbox on the GOAT tab) and gated in core (resource.extras).
FEATURE_FIELDS = {
    "x_goat_white_label": "white_label",
}


XMLRPC_TIMEOUT_SECONDS = 30.0
_LOCAL_HOSTS = {"localhost", "127.0.0.1"}


class _TimeoutMixin:
    """xmlrpc.client has no timeout of its own: a hung Odoo would block the
    nightly run forever."""

    timeout = XMLRPC_TIMEOUT_SECONDS

    def make_connection(self, host: Any) -> Any:
        conn = super().make_connection(host)  # type: ignore[misc]
        conn.timeout = self.timeout
        return conn


class _Transport(_TimeoutMixin, xmlrpc.client.Transport):
    pass


class _SafeTransport(_TimeoutMixin, xmlrpc.client.SafeTransport):
    pass


def check_odoo_url(url: str) -> str:
    """The API key travels in every XML-RPC call: refuse plain http except to
    a local Odoo."""
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return url
    if parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS:
        return url
    raise RuntimeError(
        f"ODOO_URL must use https (http is allowed only for localhost): {url!r}"
    )


def _proxy(url: str) -> xmlrpc.client.ServerProxy:
    transport = _SafeTransport() if url.startswith("https://") else _Transport()
    return xmlrpc.client.ServerProxy(url, transport=transport)


def to_iso_utc(value: Any) -> str | None:
    """Odoo's write_date ("2026-10-20 12:34:56", UTC) -> ISO 8601 UTC."""
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace(" ", "T")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


class OdooEntitlementPushParams(BaseModel):
    order_id: int = Field(
        default=0,
        description=(
            "Odoo sale.order id whose organization to push. 0 = reconcile "
            "every organization with a pushable subscription."
        ),
    )


def compute_entitlement(
    order: dict[str, Any], lines: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Compute the entitlement payload for one subscription. Pure function.

    Args:
        order: sale.order fields (subscription_state, next_invoice_date,
            x_goat_organization_id, x_goat_* overrides, feature checkboxes).
        lines: one dict per order line with ``qty`` and the product's
            ``x_goat_*`` values.

    Returns:
        The payload for POST /webhooks/odoo/entitlement, or None when the
        subscription is not in a pushable state or has no organization link.
    """
    state = order.get("subscription_state")
    if state not in PUSHABLE_STATES:
        return None
    organization_id = order.get("x_goat_organization_id")
    if not organization_id:
        return None

    payload: dict[str, Any] = {"organization_id": organization_id}

    for quota_key, field in QUOTA_FIELDS.items():
        override = order.get(field) or 0
        if override > 0:
            payload[quota_key] = override
        else:
            payload[quota_key] = sum(
                line["qty"] * (line.get(field) or 0) for line in lines
            )

    credits_override = order.get(CREDIT_FIELD) or 0
    credits = credits_override or sum(
        line["qty"] * (line.get(CREDIT_FIELD) or 0) for line in lines
    )
    if credits > 0:
        payload["total_credits"] = credits

    payload["extras"] = [
        feature for field, feature in FEATURE_FIELDS.items() if order.get(field)
    ]

    renewal = order.get("next_invoice_date")
    if renewal:
        payload["plan_renewal_date"] = str(renewal)

    payload["suspended"] = state in SUSPENDED_STATES
    # A real subscription exists, so whatever trial the org started on is
    # over — conversion clears the trial flag (and unsuspends an org that a
    # trial expiry had suspended, via `suspended` above).
    payload["on_trial"] = False
    # used_credits metering is phase 2; until then renewals have nothing to
    # reset and mid-cycle pushes must not zero anything.
    payload["reset_usage"] = False
    as_of = to_iso_utc(order.get("write_date"))
    if as_of:
        payload["as_of"] = as_of
    return payload


def merge_entitlements(
    subscriptions: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> dict[str, Any] | None:
    """One payload for an organization from all its subscriptions. Pure.

    Active (``3_progress``) subscriptions win: their quotas, credits and
    extras add up and the organization is not suspended. Without any, the most
    recently changed paused/churned one suspends it. ``as_of`` is the newest
    ``write_date`` among all the organization's subscriptions, so core can
    ignore a push that is older than what it already holds.

    Returns None when no subscription is pushable (or none has an organization).
    """
    computed = [
        (order, payload)
        for order, lines in subscriptions
        if (payload := compute_entitlement(order, lines)) is not None
    ]
    if not computed:
        return None
    active = [c for c in computed if c[0].get("subscription_state") == "3_progress"]
    if not active:
        _, latest = max(
            computed,
            key=lambda c: (
                to_iso_utc(c[0].get("write_date")) or "",
                c[0].get("id") or 0,
            ),
        )
        return latest

    first = active[0][1]
    payload: dict[str, Any] = {"organization_id": first["organization_id"]}
    for quota_key in QUOTA_FIELDS:
        payload[quota_key] = sum(p[quota_key] for _, p in active)
    credits = [p["total_credits"] for _, p in active if "total_credits" in p]
    if credits:
        payload["total_credits"] = sum(credits)
    payload["extras"] = [
        feature
        for feature in FEATURE_FIELDS.values()
        if any(feature in p["extras"] for _, p in active)
    ]
    renewals = [p["plan_renewal_date"] for _, p in active if "plan_renewal_date" in p]
    if renewals:
        payload["plan_renewal_date"] = min(renewals)  # next renewal
    payload["suspended"] = False
    payload["on_trial"] = False
    payload["reset_usage"] = False
    # The payload reflects all of the organization's subscriptions, so its time
    # is the newest change among them (a later cancellation included).
    as_ofs = [p["as_of"] for _, p in computed if "as_of" in p]
    if as_ofs:
        payload["as_of"] = max(as_ofs)
    return payload


class OdooEntitlementTask:
    """XML-RPC read from Odoo -> compute -> POST to core."""

    ORDER_FIELDS = [
        "name",
        "write_date",
        "subscription_state",
        "next_invoice_date",
        "x_goat_organization_id",
        "partner_id",
        "order_line",
        *QUOTA_FIELDS.values(),
        CREDIT_FIELD,
        *FEATURE_FIELDS.keys(),
    ]

    def __init__(self: Self) -> None:
        self.odoo_url = check_odoo_url(os.environ["ODOO_URL"].rstrip("/"))
        self.odoo_db = os.environ["ODOO_DB"]
        self.odoo_user = os.environ["ODOO_BILLING_USER"]
        self.odoo_key = os.environ["ODOO_BILLING_API_KEY"]
        # required only when actually pushing (see push_order); the CLI
        # --dry-run mode works without a running core.
        self.core_url = (os.environ.get("CORE_URL") or "").rstrip("/")
        self.webhook_secret = os.environ.get("ODOO_WEBHOOK_SECRET") or ""

        common = _proxy(f"{self.odoo_url}/xmlrpc/2/common")
        self._uid = common.authenticate(self.odoo_db, self.odoo_user, self.odoo_key, {})
        if not self._uid:
            raise RuntimeError(f"Odoo authentication failed against {self.odoo_url}")
        self._models = _proxy(f"{self.odoo_url}/xmlrpc/2/object")
        self._order_fields = self._available_order_fields()
        # goat_accounts links each customer company to its GOAT organization.
        self._partners_linked = bool(
            self._kw("res.partner", "fields_get", ["x_goat_organization_id"])
        )

    def _kw(self: Self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        return self._models.execute_kw(
            self.odoo_db, self._uid, self.odoo_key, model, method, list(args), kwargs
        )

    def _available_order_fields(self: Self) -> list[str]:
        """Intersect wanted fields with what exists (x_goat_* are manual
        fields; a missing checkbox must not break the whole push)."""
        existing = self._kw("sale.order", "fields_get", self.ORDER_FIELDS)
        missing = set(self.ORDER_FIELDS) - set(existing)
        if missing:
            logger.warning("sale.order is missing fields: %s", sorted(missing))
        return [f for f in self.ORDER_FIELDS if f in existing]

    def _organization_of_customer(self: Self, order: dict) -> str | None:
        """A subscription made in Odoo's form has no GOAT organization of its
        own: it belongs to its customer company's (set by goat_accounts)."""
        if not self._partners_linked or not order.get("partner_id"):
            return None
        partner = self._kw(
            "res.partner",
            "read",
            [order["partner_id"][0]],
            fields=["commercial_partner_id"],
        )
        if not partner or not partner[0].get("commercial_partner_id"):
            return None
        company = self._kw(
            "res.partner",
            "read",
            [partner[0]["commercial_partner_id"][0]],
            fields=["x_goat_organization_id"],
        )
        return (company[0].get("x_goat_organization_id") or None) if company else None

    def _fetch(self: Self, order_id: int) -> tuple[dict, list[dict]]:
        orders = self._kw("sale.order", "read", [order_id], fields=self._order_fields)
        if not orders:
            raise ValueError(f"sale.order {order_id} not found")
        order = orders[0]
        if not order.get("x_goat_organization_id"):
            order["x_goat_organization_id"] = self._organization_of_customer(order)

        lines: list[dict[str, Any]] = []
        line_ids = order.get("order_line") or []
        if line_ids:
            raw_lines = self._kw(
                "sale.order.line",
                "read",
                line_ids,
                fields=["product_id", "product_uom_qty"],
            )
            product_ids = [
                line["product_id"][0] for line in raw_lines if line.get("product_id")
            ]
            variants = self._kw(
                "product.product", "read", product_ids, fields=["product_tmpl_id"]
            )
            template_by_variant = {v["id"]: v["product_tmpl_id"][0] for v in variants}
            template_ids = sorted(set(template_by_variant.values()))
            wanted = [*QUOTA_FIELDS.values(), CREDIT_FIELD]
            existing = self._kw("product.template", "fields_get", wanted)
            templates = self._kw(
                "product.template",
                "read",
                template_ids,
                fields=[f for f in wanted if f in existing],
            )
            quotas_by_template = {t["id"]: t for t in templates}
            for line in raw_lines:
                if not line.get("product_id"):
                    continue
                template = quotas_by_template[
                    template_by_variant[line["product_id"][0]]
                ]
                lines.append(
                    {
                        "qty": line["product_uom_qty"],
                        **{f: template.get(f) or 0 for f in QUOTA_FIELDS.values()},
                        CREDIT_FIELD: template.get(CREDIT_FIELD) or 0,
                    }
                )
        return order, lines

    def _subscription_domain(self: Self, organization_id: str | None = None) -> list:
        """Pushable subscriptions linked to a GOAT organization (a given one,
        or any), through the order itself or its customer company."""
        op, value = ("=", organization_id) if organization_id else ("!=", False)
        own = ("x_goat_organization_id", op, value)
        partner = (
            "partner_id.commercial_partner_id.x_goat_organization_id",
            op,
            value,
        )
        return [
            ("is_subscription", "=", True),
            ("subscription_state", "in", sorted(PUSHABLE_STATES)),
            *(["|", own, partner] if self._partners_linked else [own]),
        ]

    def _organization_subscriptions(
        self: Self, organization_id: str
    ) -> list[tuple[dict, list[dict]]]:
        order_ids = self._kw(
            "sale.order", "search", self._subscription_domain(organization_id)
        )
        subscriptions = [self._fetch(order_id) for order_id in order_ids]
        # The domain also matches an order with its own, different
        # organization when its customer company points here.
        return [
            (order, lines)
            for order, lines in subscriptions
            if order.get("x_goat_organization_id") == organization_id
        ]

    def _compute_organization(
        self: Self,
        organization_id: str,
        subscriptions: list[tuple[dict, list[dict]]],
        **extra: Any,
    ) -> dict[str, Any]:
        payload = merge_entitlements(subscriptions)
        result = {
            "organization_id": organization_id,
            "orders": [order.get("name") for order, _ in subscriptions],
            **extra,
        }
        if payload is None:
            return {
                **result,
                "status": "skipped",
                "reason": "no pushable subscription",
            }
        return {**result, "status": "computed", "payload": payload}

    def compute_order(self: Self, order_id: int) -> dict[str, Any]:
        """Fetch + compute only — no POST. Computes the whole organization of
        the order (see module docstring). Used by push_order and --dry-run."""
        order, _ = self._fetch(order_id)
        organization_id = order.get("x_goat_organization_id")
        if not organization_id:
            return {
                "order_id": order_id,
                "order": order.get("name"),
                "status": "skipped",
                "reason": (f"state={order.get('subscription_state')}, org=unlinked"),
            }
        return self._compute_organization(
            organization_id,
            self._organization_subscriptions(organization_id),
            order_id=order_id,
            order=order.get("name"),
        )

    def _post(self: Self, result: dict[str, Any]) -> dict[str, Any]:
        """POST a computed organization to core; a 409 means core deleted it."""
        if not self.core_url or not self.webhook_secret:
            raise RuntimeError("CORE_URL and ODOO_WEBHOOK_SECRET are required to push")
        response = httpx.post(
            f"{self.core_url}/api/v2/webhooks/odoo/entitlement",
            headers={"X-Webhook-Secret": self.webhook_secret},
            json=result["payload"],
            timeout=30.0,
        )
        if response.status_code == 409:
            return {
                **result,
                "status": "skipped",
                "reason": "organization no longer exists in core (409)",
            }
        response.raise_for_status()
        return {**result, "status": "pushed"}

    def push_order(self: Self, order_id: int) -> dict[str, Any]:
        result = self.compute_order(order_id)
        if result["status"] == "skipped":
            return result
        return self._post(result)

    def reconcile(self: Self, dry_run: bool = False) -> dict[str, Any]:
        order_ids = self._kw("sale.order", "search", self._subscription_domain())
        errors: list[dict[str, Any]] = []
        by_organization: dict[str, list[tuple[dict, list[dict]]]] = {}
        for order_id in order_ids:
            try:
                order, lines = self._fetch(order_id)
            except Exception as exc:
                logger.exception("odoo_entitlement: reading order %s failed", order_id)
                errors.append({"order_id": order_id, "error": str(exc)})
                continue
            organization_id = order.get("x_goat_organization_id")
            if organization_id:
                by_organization.setdefault(organization_id, []).append((order, lines))

        results: list[dict[str, Any]] = []
        for organization_id, subscriptions in by_organization.items():
            try:
                result = self._compute_organization(organization_id, subscriptions)
                if result["status"] == "computed" and not dry_run:
                    result = self._post(result)
                results.append(result)
            except Exception as exc:
                logger.exception(
                    "odoo_entitlement: organization %s failed", organization_id
                )
                errors.append({"organization_id": organization_id, "error": str(exc)})
        done = sum(1 for r in results if r["status"] != "skipped")
        return {
            "status": "partial" if errors else "ok",
            "subscriptions": len(order_ids),
            "organizations": len(by_organization),
            "computed" if dry_run else "pushed": done,
            "skipped": len(results) - done,
            "errors": errors,
            "results": results,
        }


def main(
    params: OdooEntitlementPushParams = OdooEntitlementPushParams(),
) -> dict[str, Any]:
    from goatlib.tasks._db import SKIPPED, billing_enabled

    if not billing_enabled():
        return dict(SKIPPED)
    task = OdooEntitlementTask()
    if params.order_id:
        return task.push_order(params.order_id)
    return task.reconcile()


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Odoo -> GOAT entitlement push (local runner)"
    )
    parser.add_argument(
        "--order-id", type=int, default=0, help="sale.order id; 0 = reconcile all"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and print payload(s) without POSTing to core",
    )
    cli_args = parser.parse_args()

    _task = OdooEntitlementTask()
    if cli_args.dry_run:
        _result = (
            _task.compute_order(cli_args.order_id)
            if cli_args.order_id
            else _task.reconcile(dry_run=True)
        )
    else:
        _result = (
            _task.push_order(cli_args.order_id)
            if cli_args.order_id
            else _task.reconcile()
        )
    print(json.dumps(_result, indent=2, default=str))
