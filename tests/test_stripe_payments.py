"""Tests for the Stripe Payments integration."""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Patch stripe before importing our module
with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123", "STRIPE_WEBHOOK_SECRET": "whsec_123"}):
    from core.stripe_payments import (
        TIER_CONFIG,
        VALID_TIERS,
        claim_guarantee,
        change_tier,
        create_checkout_session,
        create_customer_record,
        ensure_customer_table,
        get_customer_by_email,
        get_customer_by_stripe_id,
        handle_checkout_completed,
        list_customers,
        process_webhook,
        update_customer_subscription,
        update_customer_tier,
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_customers_table():
    """Ensure customers table exists and is clean before each test."""
    ensure_customer_table()
    # Clean up any test data
    from core.database import _run_team_db
    _run_team_db("DELETE FROM customers WHERE email LIKE 'test_%'")
    yield


# ── Configuration Tests ──────────────────────────────────────────────────────

def test_valid_tiers():
    assert VALID_TIERS == {"starter", "pro", "autopilot"}


def test_tier_config():
    assert TIER_CONFIG["starter"]["amount"] == 2900
    assert TIER_CONFIG["pro"]["amount"] == 7900
    assert TIER_CONFIG["autopilot"]["amount"] == 19900


# ── Database CRUD Tests ──────────────────────────────────────────────────────

def test_create_customer_record():
    cid = create_customer_record(
        snapshot_id="snap-123",
        email="test_create@example.com",
        business_name="Test Biz",
        tier="starter",
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
    )
    assert len(cid) == 36  # UUID

    customer = get_customer_by_stripe_id("cus_123")
    assert customer is not None
    assert customer["email"] == "test_create@example.com"
    assert customer["tier"] == "starter"
    assert customer["status"] == "active"
    assert customer["guarantee_claimed"] == 0
    assert customer["guarantee_until"] is not None


def test_get_customer_by_email():
    create_customer_record(
        snapshot_id=None,
        email="test_email@example.com",
        business_name="Email Biz",
        tier="pro",
        stripe_customer_id="cus_email",
    )
    customer = get_customer_by_email("test_email@example.com")
    assert customer is not None
    assert customer["business_name"] == "Email Biz"
    assert customer["tier"] == "pro"


def test_update_customer_subscription():
    create_customer_record(
        snapshot_id=None,
        email="test_update@example.com",
        stripe_customer_id="cus_update",
        tier="starter",
    )
    update_customer_subscription(
        stripe_customer_id="cus_update",
        stripe_subscription_id="sub_new",
        tier="pro",
        status="active",
        current_period_start="2024-01-01T00:00:00+00:00",
        current_period_end="2024-02-01T00:00:00+00:00",
        cancel_at_period_end=True,
    )
    customer = get_customer_by_stripe_id("cus_update")
    assert customer["tier"] == "pro"
    assert customer["stripe_subscription_id"] == "sub_new"
    assert customer["status"] == "active"
    assert customer["current_period_start"] == "2024-01-01T00:00:00+00:00"
    assert customer["current_period_end"] == "2024-02-01T00:00:00+00:00"
    assert customer["cancel_at_period_end"] == 1


def test_update_customer_tier():
    create_customer_record(
        snapshot_id=None,
        email="test_tier@example.com",
        stripe_customer_id="cus_tier",
        tier="starter",
    )
    update_customer_tier("cus_tier", "autopilot")
    customer = get_customer_by_stripe_id("cus_tier")
    assert customer["tier"] == "autopilot"


def test_list_customers():
    create_customer_record(snapshot_id=None, email="test_a@example.com", stripe_customer_id="cus_a", tier="starter")
    create_customer_record(snapshot_id=None, email="test_b@example.com", stripe_customer_id="cus_b", tier="pro", status="canceled")
    all_customers = list_customers()
    assert len(all_customers) >= 2
    active = list_customers(status="active")
    assert any(c["stripe_customer_id"] == "cus_a" for c in active)
    canceled = list_customers(status="canceled")
    assert any(c["stripe_customer_id"] == "cus_b" for c in canceled)


# ── Guarantee Tests ──────────────────────────────────────────────────────────

def test_claim_guarantee_success():
    create_customer_record(
        snapshot_id=None,
        email="test_guarantee@example.com",
        stripe_customer_id="cus_guarantee",
        tier="starter",
    )
    ok = claim_guarantee("cus_guarantee")
    assert ok is True
    customer = get_customer_by_stripe_id("cus_guarantee")
    assert customer["guarantee_claimed"] == 1


def test_claim_guarantee_already_claimed():
    create_customer_record(
        snapshot_id=None,
        email="test_guarantee2@example.com",
        stripe_customer_id="cus_guarantee2",
        tier="starter",
    )
    claim_guarantee("cus_guarantee2")
    ok = claim_guarantee("cus_guarantee2")
    assert ok is False


def test_claim_guarantee_nonexistent():
    ok = claim_guarantee("cus_does_not_exist")
    assert ok is False


# ── Checkout Session Tests ───────────────────────────────────────────────────

@patch("core.stripe_payments.stripe.checkout.Session.create")
def test_create_checkout_session_with_price_id(mock_create):
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test"
    mock_session.id = "cs_test_123"
    mock_create.return_value = mock_session

    with patch.dict("core.stripe_payments.TIER_PRICES", {"starter": "price_123", "pro": "", "autopilot": ""}):
        session = create_checkout_session(
            tier="starter",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            customer_email="test@example.com",
            snapshot_id="snap-123",
        )

    assert session.url == "https://checkout.stripe.com/test"
    assert session.id == "cs_test_123"
    call_args = mock_create.call_args[1]
    assert call_args["mode"] == "subscription"
    assert call_args["success_url"] == "https://example.com/success"
    assert call_args["customer_email"] == "test@example.com"
    assert call_args["metadata"]["tier"] == "starter"
    assert call_args["metadata"]["snapshot_id"] == "snap-123"


@patch("core.stripe_payments.stripe.checkout.Session.create")
def test_create_checkout_session_inline_price(mock_create):
    """Test fallback inline price when no Price ID is configured."""
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test"
    mock_session.id = "cs_test_456"
    mock_create.return_value = mock_session

    with patch.dict("core.stripe_payments.TIER_PRICES", {"starter": "", "pro": "", "autopilot": ""}):
        session = create_checkout_session(
            tier="pro",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )

    assert session.id == "cs_test_456"
    call_args = mock_create.call_args[1]
    line_item = call_args["line_items"][0]
    assert line_item["price_data"]["currency"] == "usd"
    assert line_item["price_data"]["unit_amount"] == 7900


def test_create_checkout_session_invalid_tier():
    with pytest.raises(ValueError, match="Invalid tier"):
        create_checkout_session(
            tier="invalid",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )


# ── Webhook Tests ────────────────────────────────────────────────────────────

@patch("core.stripe_payments.stripe.Subscription.retrieve")
def test_handle_checkout_completed(mock_sub_retrieve):
    mock_sub = {
        "current_period_start": 1704067200,
        "current_period_end": 1706745600,
    }
    mock_sub_retrieve.return_value = mock_sub

    event = {
        "data": {
            "object": {
                "customer_email": "webhook_test@example.com",
                "customer": "cus_webhook",
                "subscription": "sub_webhook",
                "metadata": {"tier": "pro", "snapshot_id": "snap-wb"},
            }
        }
    }

    result = handle_checkout_completed(event)
    assert result["stripe_customer_id"] == "cus_webhook"
    assert result["tier"] == "pro"

    customer = get_customer_by_stripe_id("cus_webhook")
    assert customer is not None
    assert customer["email"] == "webhook_test@example.com"
    assert customer["tier"] == "pro"
    assert customer["snapshot_id"] == "snap-wb"


@patch("core.stripe_payments.stripe.Subscription.retrieve")
def test_handle_checkout_completed_existing_customer(mock_sub_retrieve):
    """Webhook should update existing customer rather than create duplicate."""
    create_customer_record(
        snapshot_id="snap-old",
        email="existing@example.com",
        stripe_customer_id="cus_existing",
        tier="starter",
    )
    mock_sub_retrieve.return_value = {
        "current_period_start": 1704067200,
        "current_period_end": 1706745600,
    }

    event = {
        "data": {
            "object": {
                "customer_email": "existing@example.com",
                "customer": "cus_existing",
                "subscription": "sub_new",
                "metadata": {"tier": "autopilot"},
            }
        }
    }

    result = handle_checkout_completed(event)
    assert result["tier"] == "autopilot"

    customer = get_customer_by_stripe_id("cus_existing")
    assert customer["tier"] == "autopilot"
    assert customer["stripe_subscription_id"] == "sub_new"


def test_process_webhook_unhandled_type():
    event = {"type": "invoice.finalized"}
    result = process_webhook(event)
    assert result["handled"] is False
    assert result["type"] == "invoice.finalized"


def test_process_webhook_invoice_paid():
    with patch("core.stripe_payments.get_customer_by_stripe_id") as mock_get:
        mock_get.return_value = {"stripe_customer_id": "cus_inv"}
        with patch("core.stripe_payments._run_team_db") as mock_db:
            event = {
                "type": "invoice.paid",
                "data": {
                    "object": {
                        "customer": "cus_inv",
                        "period_start": 1704067200,
                        "period_end": 1706745600,
                    }
                },
            }
            result = process_webhook(event)
            assert result["handled"] is True
            mock_db.assert_called_once()


def test_process_webhook_subscription_deleted():
    with patch("core.stripe_payments.get_customer_by_stripe_id") as mock_get:
        mock_get.return_value = {"stripe_customer_id": "cus_del"}
        with patch("core.stripe_payments._run_team_db") as mock_db:
            event = {
                "type": "customer.subscription.deleted",
                "data": {"object": {"customer": "cus_del"}},
            }
            result = process_webhook(event)
            assert result["handled"] is True
            mock_db.assert_called_once()


# ── Upgrade / Downgrade Tests ────────────────────────────────────────────────

@patch("core.stripe_payments.stripe.Subscription.retrieve")
@patch("core.stripe_payments.stripe.Subscription.modify")
def test_change_tier(mock_modify, mock_retrieve):
    create_customer_record(
        snapshot_id=None,
        email="test_change@example.com",
        stripe_customer_id="cus_change",
        stripe_subscription_id="sub_change",
        tier="starter",
    )
    mock_retrieve.return_value = {"items": {"data": [{"id": "si_123"}]}}
    mock_modify.return_value = None

    with patch.dict("core.stripe_payments.TIER_PRICES", {"starter": "price_starter", "pro": "price_pro", "autopilot": "price_autopilot"}):
        result = change_tier("cus_change", "pro")

    assert result["old_tier"] == "starter"
    assert result["new_tier"] == "pro"
    assert result["status"] == "updated"
    mock_modify.assert_called_once()

    customer = get_customer_by_stripe_id("cus_change")
    assert customer["tier"] == "pro"


def test_change_tier_invalid_tier():
    with pytest.raises(ValueError, match="Invalid tier"):
        change_tier("cus_123", "invalid")


def test_change_tier_customer_not_found():
    with pytest.raises(ValueError, match="Customer not found"):
        change_tier("cus_nonexistent", "pro")


def test_change_tier_no_subscription():
    create_customer_record(
        snapshot_id=None,
        email="test_nosub@example.com",
        stripe_customer_id="cus_nosub",
        tier="starter",
    )
    with pytest.raises(ValueError, match="no active subscription"):
        change_tier("cus_nosub", "pro")


# ── Flask Route Tests ────────────────────────────────────────────────────────

from web.app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@patch("web.app.create_checkout_session")
def test_api_checkout_create(mock_session, client):
    mock_session.return_value = MagicMock(url="https://checkout.stripe.com/test", id="cs_test")
    resp = client.post(
        "/api/checkout/create",
        json={
            "tier": "pro",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
            "email": "route_test@example.com",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["checkout_url"] == "https://checkout.stripe.com/test"
    assert data["session_id"] == "cs_test"


def test_api_checkout_create_missing_fields(client):
    resp = client.post("/api/checkout/create", json={"tier": "starter"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "success_url" in data["error"]


def test_api_checkout_create_invalid_tier(client):
    resp = client.post(
        "/api/checkout/create",
        json={
            "tier": "invalid",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        },
    )
    assert resp.status_code == 400


@patch("web.app.construct_event")
@patch("web.app.process_webhook")
def test_api_stripe_webhook(mock_process, mock_construct, client):
    mock_construct.return_value = {"type": "checkout.session.completed"}
    mock_process.return_value = {"customer_id": "cust_123"}
    resp = client.post(
        "/api/webhooks/stripe",
        data=b"test_payload",
        headers={"Stripe-Signature": "sig_test"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["result"]["customer_id"] == "cust_123"


@patch("web.app.claim_guarantee")
def test_api_claim_guarantee(mock_claim, client):
    mock_claim.return_value = True
    resp = client.post(
        "/api/customers/claim-guarantee",
        json={"stripe_customer_id": "cus_guar"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "Refund" in data["message"]


@patch("web.app.claim_guarantee")
def test_api_claim_guarantee_not_eligible(mock_claim, client):
    mock_claim.return_value = False
    resp = client.post(
        "/api/customers/claim-guarantee",
        json={"stripe_customer_id": "cus_guar"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


@patch("web.app.get_customer_by_email")
def test_api_customer_me(mock_get, client):
    mock_get.return_value = {"email": "me@example.com", "tier": "pro"}
    resp = client.get("/api/customers/me?email=me@example.com")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["customer"]["tier"] == "pro"


@patch("web.app.list_customers")
def test_api_customers_list(mock_list, client):
    mock_list.return_value = [{"email": "a@example.com"}, {"email": "b@example.com"}]
    resp = client.get("/api/customers?status=active")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["customers"]) == 2


@patch("web.app.change_tier")
def test_api_change_tier(mock_change, client):
    mock_change.return_value = {"old_tier": "starter", "new_tier": "pro", "status": "updated"}
    resp = client.post(
        "/api/customers/change-tier",
        json={"stripe_customer_id": "cus_change", "tier": "pro"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["new_tier"] == "pro"
