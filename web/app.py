"""LocalPulse AI — Landing Page & API Server

A lightweight Flask app that serves the report request landing page,
handles form submissions, and manages Stripe subscriptions.

Usage:
    python web/app.py

Environment:
    PORT        — HTTP port (default: 5000)
    HOST        — Bind address (default: 0.0.0.0)
    TRIGGER     — Set to "1" to auto-run pipeline after submission
    STRIPE_SECRET_KEY     — Stripe secret key
    STRIPE_WEBHOOK_SECRET — Stripe webhook endpoint secret
"""
import json
import logging
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Add project root to path so core/ imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import create_snapshot, update_snapshot_data
from core.email_service import (
    process_resend_webhook,
    send_snapshot_report,
    send_upgrade_confirmation,
    send_welcome,
)
from core.stripe_payments import (
    claim_guarantee,
    change_tier,
    create_checkout_session,
    get_customer_by_email,
    get_customer_by_stripe_id,
    list_customers,
    process_webhook,
    construct_event,
)
from scripts.run_pipeline import run_full_pipeline

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "web" / "templates"),
    static_folder=str(PROJECT_ROOT / "web" / "static"),
)
app.config["JSON_SORT_KEYS"] = False

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the landing page."""
    return render_template("index.html")


@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "localpulse-landing"})


@app.route("/api/request-report", methods=["POST"])
def request_report():
    """Handle report request form submission.

    Expected JSON body:
        {
            "business_name": str,
            "email": str,
            "city": str,
            "state": str,
            "niche": str,
            "website": str (optional)
        }

    Returns:
        { "success": true, "snapshot_id": str, "message": str }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    # ── Validate required fields ────────────────────────────────────────────
    required = ["business_name", "email", "city", "state", "niche"]
    missing = [f for f in required if not data.get(f) or not str(data.get(f)).strip()]
    if missing:
        return jsonify(
            {"success": False, "error": f"Missing required fields: {', '.join(missing)}"}
        ), 400

    business_name = str(data["business_name"]).strip()
    email = str(data["email"]).strip()
    city = str(data["city"]).strip()
    state = str(data["state"]).strip()
    niche = str(data["niche"]).strip()
    website = str(data.get("website", "")).strip()

    # Basic email validation
    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"success": False, "error": "Invalid email address"}), 400

    location = f"{city}, {state}"

    try:
        # Create pending snapshot
        snap_id = create_snapshot(
            business_name=business_name,
            location=location,
            website=website,
        )

        # Enrich snapshot data with requester info
        update_snapshot_data(snap_id, "requester_email", email)
        update_snapshot_data(snap_id, "niche", niche)
        update_snapshot_data(snap_id, "requested_at", _now_iso())

        logger.info(f"Created snapshot {snap_id} for {business_name} in {location}")

        # Send immediate welcome email
        try:
            send_welcome(to_email=email, business_name=business_name)
            logger.info(f"Welcome email sent to {email}")
        except Exception as e:
            logger.warning(f"Welcome email failed for {email}: {e}")

        # Optionally trigger pipeline
        if os.environ.get("TRIGGER", "").lower() in ("1", "true", "yes"):
            try:
                results = run_full_pipeline(max_per_stage=1)
                logger.info(f"Auto-triggered pipeline: {results}")
            except Exception as e:
                logger.warning(f"Pipeline auto-trigger failed: {e}")

        return jsonify({
            "success": True,
            "snapshot_id": snap_id,
            "message": (
                f"Thanks, {business_name}! Your Business Health Snapshot is being prepared. "
                f"We'll email the report to {email} within minutes."
            ),
        })

    except Exception as e:
        logger.exception("Failed to create snapshot")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/status/<snapshot_id>")
def snapshot_status(snapshot_id: str):
    """Check the status of a snapshot."""
    from core.database import get_snapshot

    snapshot = get_snapshot(snapshot_id)
    if not snapshot:
        return jsonify({"success": False, "error": "Snapshot not found"}), 404

    data = snapshot.get("data", {}) or {}
    return jsonify({
        "success": True,
        "snapshot_id": snapshot_id,
        "status": snapshot["status"],
        "business_name": snapshot["business_name"],
        "created_at": snapshot["created_at"],
        "has_scout_data": "scout_data" in data,
        "has_scoring": "scoring_output" in data,
        "has_roadmap": "growth_roadmap" in data,
        "has_deliverables": "draft_deliverables" in data,
    })


# ─── Stripe Checkout ──────────────────────────────────────────────────────────

@app.route("/api/checkout/create", methods=["POST"])
def checkout_create():
    """Create a Stripe Checkout session for a subscription tier.

    Expected JSON body:
        {
            "tier": str ("starter" | "pro" | "autopilot"),
            "email": str (optional),
            "snapshot_id": str (optional),
            "success_url": str,
            "cancel_url": str
        }

    Returns:
        { "success": true, "checkout_url": str, "session_id": str }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    tier = data.get("tier", "").lower().strip()
    if tier not in ("starter", "pro", "autopilot"):
        return jsonify({"success": False, "error": "Invalid tier"}), 400

    success_url = data.get("success_url", "")
    cancel_url = data.get("cancel_url", "")
    if not success_url or not cancel_url:
        return jsonify({"success": False, "error": "success_url and cancel_url are required"}), 400

    try:
        session = create_checkout_session(
            tier=tier,
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=data.get("email"),
            snapshot_id=data.get("snapshot_id"),
        )
        return jsonify({
            "success": True,
            "checkout_url": session.url,
            "session_id": session.id,
        })
    except Exception as e:
        logger.exception("Failed to create checkout session")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/webhooks/resend", methods=["POST"])
def resend_webhook():
    """Handle Resend webhook events (delivery, open, click, bounce).

    Updates email_logs status for analytics tracking.
    """
    payload = request.get_json(force=True, silent=True) or {}
    try:
        result = process_resend_webhook(payload)
        return jsonify(result)
    except Exception as e:
        logger.exception("Resend webhook processing failed")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events.

    Verifies the signature and dispatches to the correct handler.
    Also triggers upgrade confirmation email on successful checkout.
    """
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = construct_event(payload, sig_header)
        result = process_webhook(event)

        # Send upgrade confirmation on successful checkout
        if event.get("type") == "checkout.session.completed":
            session_obj = event.get("data", {}).get("object", {})
            customer_email = session_obj.get("customer_email", "")
            customer_id = session_obj.get("customer", "")
            metadata = session_obj.get("metadata", {})
            tier = metadata.get("tier", "")
            if customer_email and tier:
                try:
                    send_upgrade_confirmation(
                        to_email=customer_email,
                        tier=tier,
                        stripe_customer_id=customer_id,
                    )
                    logger.info(f"Upgrade confirmation sent to {customer_email} for {tier}")
                except Exception as e:
                    logger.warning(f"Upgrade confirmation failed for {customer_email}: {e}")

        return jsonify({"success": True, "result": result})
    except ValueError as e:
        logger.warning(f"Invalid payload: {e}")
        return jsonify({"success": False, "error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Invalid signature: {e}")
        return jsonify({"success": False, "error": "Invalid signature"}), 400
    except Exception as e:
        logger.exception("Webhook processing failed")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/customers/change-tier", methods=["POST"])
def customer_change_tier():
    """Upgrade or downgrade a customer's subscription tier.

    Expected JSON body:
        { "stripe_customer_id": str, "tier": str }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    stripe_customer_id = data.get("stripe_customer_id", "").strip()
    tier = data.get("tier", "").lower().strip()

    if not stripe_customer_id or not tier:
        return jsonify({"success": False, "error": "stripe_customer_id and tier are required"}), 400

    try:
        result = change_tier(stripe_customer_id, tier)
        return jsonify({"success": True, **result})
    except Exception as e:
        logger.exception("Failed to change tier")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/customers/claim-guarantee", methods=["POST"])
def customer_claim_guarantee():
    """Claim the 30-day "Lead Leak" money-back guarantee.

    Expected JSON body:
        { "stripe_customer_id": str }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    stripe_customer_id = data.get("stripe_customer_id", "").strip()
    if not stripe_customer_id:
        return jsonify({"success": False, "error": "stripe_customer_id is required"}), 400

    try:
        ok = claim_guarantee(stripe_customer_id)
        if not ok:
            return jsonify({"success": False, "error": "Guarantee not eligible or already claimed"}), 400
        return jsonify({"success": True, "message": "Guarantee claimed successfully. Refund will be processed within 5 business days."})
    except Exception as e:
        logger.exception("Failed to claim guarantee")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/customers/me", methods=["GET"])
def customer_me():
    """Get the current customer's subscription details by email."""
    email = request.args.get("email", "").strip()
    if not email:
        return jsonify({"success": False, "error": "email query param is required"}), 400

    customer = get_customer_by_email(email)
    if not customer:
        return jsonify({"success": False, "error": "Customer not found"}), 404

    return jsonify({"success": True, "customer": customer})


@app.route("/api/customers", methods=["GET"])
def customers_list():
    """List all customers, optionally filtered by status."""
    status = request.args.get("status")
    customers = list_customers(status=status)
    return jsonify({"success": True, "customers": customers})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ─── Entrypoint ───────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info(f"Starting LocalPulse landing server on {host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
