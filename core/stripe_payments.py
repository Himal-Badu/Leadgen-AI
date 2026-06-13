"""Stripe Payments Integration for LocalPulse AI.

Handles Checkout sessions, webhook events, subscription tier management,
and 30-day guarantee tracking.

Environment:
    STRIPE_SECRET_KEY     — Stripe secret key (test or live)
    STRIPE_WEBHOOK_SECRET — Endpoint secret for webhook verification
    STRIPE_PRICE_STARTER  — Price ID for Starter tier ($29/mo)
    STRIPE_PRICE_PRO      — Price ID for Pro tier ($79/mo)
    STRIPE_PRICE_AUTOPILOT — Price ID for Autopilot tier ($199/mo)
"""
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import stripe

from core.database import _run_team_db

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

TIER_PRICES = {
    "starter": os.environ.get("STRIPE_PRICE_STARTER", ""),
    "pro": os.environ.get("STRIPE_PRICE_PRO", ""),
    "autopilot": os.environ.get("STRIPE_PRICE_AUTOPILOT", ""),
}

TIER_CONFIG = {
    "starter": {"name": "LocalPulse Starter", "amount": 2900, "interval": "month"},
    "pro": {"name": "LocalPulse Pro", "amount": 7900, "interval": "month"},
    "autopilot": {"name": "LocalPulse Autopilot", "amount": 19900, "interval": "month"},
}

VALID_TIERS = set(TIER_CONFIG.keys())


# ── Database ─────────────────────────────────────────────────────────────────

def _esc(value: str) -> str:
    return value.replace("'", "''")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_customer_table() -> None:
    """Create the customers table if it doesn't exist."""
    sql = """
    CREATE TABLE IF NOT EXISTS customers (
        id TEXT PRIMARY KEY,
        snapshot_id TEXT,
        stripe_customer_id TEXT,
        stripe_subscription_id TEXT,
        email TEXT NOT NULL,
        business_name TEXT,
        tier TEXT,
        status TEXT DEFAULT 'active',
        subscribed_at TEXT,
        current_period_start TEXT,
        current_period_end TEXT,
        cancel_at_period_end INTEGER DEFAULT 0,
        guarantee_until TEXT,
        guarantee_claimed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """
    _run_team_db(sql)


def create_customer_record(
    snapshot_id: Optional[str],
    email: str,
    business_name: str = "",
    tier: str = "",
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    status: str = "active",
) -> str:
    """Create a customer record in the DB. Returns the customer ID."""
    ensure_customer_table()
    customer_id = str(uuid.uuid4())
    now = _now_iso()
    guarantee = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    sql = (
        f"INSERT INTO customers (id, snapshot_id, email, business_name, tier, "
        f"stripe_customer_id, stripe_subscription_id, status, subscribed_at, guarantee_until, created_at, updated_at) "
        f"VALUES ("
        f"'{customer_id}', "
        f"'{snapshot_id or ''}', "
        f"'{_esc(email)}', "
        f"'{_esc(business_name)}', "
        f"'{tier}', "
        f"'{stripe_customer_id}', "
        f"'{stripe_subscription_id}', "
        f"'{status}', "
        f"'{now}', "
        f"'{guarantee}', "
        f"'{now}', "
        f"'{now}'"
        f")"
    )
    _run_team_db(sql)
    return customer_id


def get_customer_by_stripe_id(stripe_customer_id: str) -> Optional[dict[str, Any]]:
    """Find a customer by their Stripe customer ID."""
    ensure_customer_table()
    rows = _run_team_db(
        f"SELECT * FROM customers WHERE stripe_customer_id = '{stripe_customer_id}'"
    )
    if not rows:
        return None
    return rows[0]


def get_customer_by_email(email: str) -> Optional[dict[str, Any]]:
    """Find a customer by email."""
    ensure_customer_table()
    rows = _run_team_db(
        f"SELECT * FROM customers WHERE email = '{_esc(email)}' ORDER BY created_at DESC LIMIT 1"
    )
    if not rows:
        return None
    return rows[0]


def update_customer_subscription(
    stripe_customer_id: str,
    stripe_subscription_id: str,
    tier: str,
    status: str = "active",
    current_period_start: Optional[str] = None,
    current_period_end: Optional[str] = None,
    cancel_at_period_end: bool = False,
) -> None:
    """Update customer record with subscription details."""
    ensure_customer_table()
    now = _now_iso()
    cancel = 1 if cancel_at_period_end else 0
    sql = (
        f"UPDATE customers SET "
        f"stripe_subscription_id = '{stripe_subscription_id}', "
        f"tier = '{tier}', "
        f"status = '{status}', "
        f"updated_at = '{now}', "
        f"cancel_at_period_end = {cancel}"
    )
    if current_period_start:
        sql += f", current_period_start = '{current_period_start}'"
    if current_period_end:
        sql += f", current_period_end = '{current_period_end}'"
    sql += f" WHERE stripe_customer_id = '{stripe_customer_id}'"
    _run_team_db(sql)


def update_customer_tier(stripe_customer_id: str, tier: str) -> None:
    """Update a customer's subscription tier (upgrade/downgrade)."""
    ensure_customer_table()
    now = _now_iso()
    _run_team_db(
        f"UPDATE customers SET tier = '{tier}', updated_at = '{now}' "
        f"WHERE stripe_customer_id = '{stripe_customer_id}'"
    )


def claim_guarantee(stripe_customer_id: str) -> bool:
    """Claim the 30-day guarantee refund. Returns True if successful."""
    ensure_customer_table()
    customer = get_customer_by_stripe_id(stripe_customer_id)
    if not customer:
        return False
    if customer.get("guarantee_claimed"):
        return False
    guarantee = customer.get("guarantee_until")
    if not guarantee or guarantee < _now_iso():
        return False
    now = _now_iso()
    _run_team_db(
        f"UPDATE customers SET guarantee_claimed = 1, updated_at = '{now}' "
        f"WHERE stripe_customer_id = '{stripe_customer_id}'"
    )
    return True


def list_customers(status: Optional[str] = None) -> list[dict[str, Any]]:
    """List all customers, optionally filtered by status."""
    ensure_customer_table()
    if status:
        rows = _run_team_db(
            f"SELECT * FROM customers WHERE status = '{status}' ORDER BY created_at DESC"
        )
    else:
        rows = _run_team_db("SELECT * FROM customers ORDER BY created_at DESC")
    return rows


# ── Stripe Checkout ──────────────────────────────────────────────────────────

def create_checkout_session(
    tier: str,
    success_url: str,
    cancel_url: str,
    customer_email: Optional[str] = None,
    snapshot_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create a Stripe Checkout session for a subscription tier.

    Returns the session object from Stripe.
    """
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier: {tier}. Must be one of {VALID_TIERS}")

    if not stripe.api_key:
        raise RuntimeError("Stripe secret key not configured")

    price_id = TIER_PRICES.get(tier, "")
    if not price_id:
        # Fallback: use inline price for testing
        mode = "subscription"
        line_items = [{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": TIER_CONFIG[tier]["name"]},
                "unit_amount": TIER_CONFIG[tier]["amount"],
                "recurring": {"interval": TIER_CONFIG[tier]["interval"]},
            },
            "quantity": 1,
        }]
    else:
        mode = "subscription"
        line_items = [{"price": price_id, "quantity": 1}]

    metadata = {"tier": tier}
    if snapshot_id:
        metadata["snapshot_id"] = snapshot_id

    params = {
        "payment_method_types": ["card"],
        "line_items": line_items,
        "mode": mode,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        "subscription_data": {
            "metadata": metadata,
        },
    }
    if customer_email:
        params["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**params)
    return session


# ── Webhook Handling ─────────────────────────────────────────────────────────

def construct_event(payload: bytes, sig_header: str) -> stripe.Event:
    """Verify and construct a Stripe webhook event."""
    if not WEBHOOK_SECRET:
        raise RuntimeError("Webhook secret not configured")
    return stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)


def handle_checkout_completed(event: stripe.Event) -> dict[str, Any]:
    """Process checkout.session.completed webhook.

    Creates or updates customer record and returns the customer info.
    """
    session = event["data"]["object"]
    customer_email = session.get("customer_email", "")
    stripe_customer_id = session.get("customer", "")
    stripe_subscription_id = session.get("subscription", "")
    metadata = session.get("metadata", {}) or {}
    tier = metadata.get("tier", "")
    snapshot_id = metadata.get("snapshot_id", "")

    logger.info(
        f"Checkout completed: customer={stripe_customer_id} tier={tier} "
        f"subscription={stripe_subscription_id}"
    )

    # Fetch subscription details for period info
    period_start = None
    period_end = None
    if stripe_subscription_id:
        try:
            sub = stripe.Subscription.retrieve(stripe_subscription_id)
            period_start = datetime.fromtimestamp(
                sub["current_period_start"], tz=timezone.utc
            ).isoformat()
            period_end = datetime.fromtimestamp(
                sub["current_period_end"], tz=timezone.utc
            ).isoformat()
        except Exception as e:
            logger.warning(f"Could not fetch subscription details: {e}")

    existing = get_customer_by_stripe_id(stripe_customer_id)
    if existing:
        update_customer_subscription(
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            tier=tier,
            status="active",
            current_period_start=period_start,
            current_period_end=period_end,
        )
        customer_id = existing["id"]
    else:
        customer_id = create_customer_record(
            snapshot_id=snapshot_id,
            email=customer_email,
            tier=tier,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            status="active",
        )
        if period_start:
            update_customer_subscription(
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                tier=tier,
                status="active",
                current_period_start=period_start,
                current_period_end=period_end,
            )

    return {
        "customer_id": customer_id,
        "stripe_customer_id": stripe_customer_id,
        "tier": tier,
        "status": "active",
    }


def handle_invoice_paid(event: stripe.Event) -> None:
    """Process invoice.paid — extend current period."""
    invoice = event["data"]["object"]
    stripe_customer_id = invoice.get("customer", "")
    period_start = datetime.fromtimestamp(
        invoice["period_start"], tz=timezone.utc
    ).isoformat()
    period_end = datetime.fromtimestamp(
        invoice["period_end"], tz=timezone.utc
    ).isoformat()

    customer = get_customer_by_stripe_id(stripe_customer_id)
    if customer:
        _run_team_db(
            f"UPDATE customers SET current_period_start = '{period_start}', "
            f"current_period_end = '{period_end}', updated_at = '{_now_iso()}' "
            f"WHERE stripe_customer_id = '{stripe_customer_id}'"
        )
        logger.info(f"Invoice paid for customer {stripe_customer_id}, period extended")


def handle_subscription_deleted(event: stripe.Event) -> None:
    """Process customer.subscription.deleted — mark as canceled."""
    subscription = event["data"]["object"]
    stripe_customer_id = subscription.get("customer", "")
    customer = get_customer_by_stripe_id(stripe_customer_id)
    if customer:
        _run_team_db(
            f"UPDATE customers SET status = 'canceled', updated_at = '{_now_iso()}' "
            f"WHERE stripe_customer_id = '{stripe_customer_id}'"
        )
        logger.info(f"Subscription deleted for customer {stripe_customer_id}")


def process_webhook(event: stripe.Event) -> dict[str, Any]:
    """Dispatch a verified Stripe webhook event to the correct handler."""
    event_type = event.get("type", "")
    logger.info(f"Processing webhook: {event_type}")

    if event_type == "checkout.session.completed":
        return handle_checkout_completed(event)
    elif event_type == "invoice.paid":
        handle_invoice_paid(event)
        return {"handled": True, "type": event_type}
    elif event_type == "customer.subscription.deleted":
        handle_subscription_deleted(event)
        return {"handled": True, "type": event_type}
    else:
        logger.info(f"Unhandled webhook type: {event_type}")
        return {"handled": False, "type": event_type}


# ── Upgrade / Downgrade ──────────────────────────────────────────────────────

def change_tier(stripe_customer_id: str, new_tier: str) -> dict[str, Any]:
    """Upgrade or downgrade a customer's subscription to a new tier.

    Uses Stripe's subscription update API to change the price item.
    """
    if new_tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier: {new_tier}")

    customer = get_customer_by_stripe_id(stripe_customer_id)
    if not customer:
        raise ValueError(f"Customer not found: {stripe_customer_id}")

    subscription_id = customer.get("stripe_subscription_id", "")
    if not subscription_id:
        raise ValueError("Customer has no active subscription")

    price_id = TIER_PRICES.get(new_tier, "")
    if not price_id:
        raise ValueError(f"No Stripe Price ID configured for tier: {new_tier}")

    # Update the subscription's items to the new price
    subscription = stripe.Subscription.retrieve(subscription_id)
    item_id = subscription["items"]["data"][0]["id"]

    stripe.Subscription.modify(
        subscription_id,
        items=[{"id": item_id, "price": price_id}],
        metadata={"tier": new_tier},
        proration_behavior="create_prorations",
    )

    update_customer_tier(stripe_customer_id, new_tier)
    logger.info(f"Changed tier for {stripe_customer_id} to {new_tier}")

    return {
        "stripe_customer_id": stripe_customer_id,
        "old_tier": customer.get("tier", ""),
        "new_tier": new_tier,
        "status": "updated",
    }
