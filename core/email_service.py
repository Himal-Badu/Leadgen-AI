"""Email Service — Unified transactional email client for LocalPulse AI.

Uses Resend (resend.com) for delivery. All methods accept a `dry_run` flag
for safe previewing without API calls.

Environment:
    RESEND_API_KEY   — Resend API key
    EMAIL_FROM       — Verified sender (default: alex@localpulse.ai)
    EMAIL_FROM_NAME  — Display name (default: Alex from LocalPulse)
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import resend
except ImportError:  # pragma: no cover
    resend = None

from core.database import _run_team_db, get_snapshot, update_snapshot_data
from core.report_renderer import (
    render_followup_email,
    render_snapshot_report,
    render_upgrade_confirmation,
    render_welcome_email,
)

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "alex@localpulse.ai")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Alex from LocalPulse")


# ── DB Helpers ───────────────────────────────────────────────────────────────

def _esc(value: str) -> str:
    return value.replace("'", "''")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_email_log_table() -> None:
    """Create email_logs table for delivery tracking."""
    sql = """
    CREATE TABLE IF NOT EXISTS email_logs (
        id TEXT PRIMARY KEY,
        outreach_id TEXT,
        snapshot_id TEXT,
        recipient_email TEXT NOT NULL,
        email_type TEXT,
        subject TEXT,
        resend_message_id TEXT,
        sequence_day INTEGER DEFAULT 0,
        status TEXT DEFAULT 'drafted',
        opened_at TEXT,
        clicked_at TEXT,
        bounced_at TEXT,
        sent_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """
    _run_team_db(sql)


def log_email(
    outreach_id: Optional[str],
    snapshot_id: Optional[str],
    recipient_email: str,
    email_type: str,
    subject: str,
    resend_message_id: str,
    sequence_day: int = 0,
) -> str:
    """Log an email send to the database."""
    ensure_email_log_table()
    log_id = str(uuid.uuid4())
    now = _now_iso()
    sql = (
        f"INSERT INTO email_logs (id, outreach_id, snapshot_id, recipient_email, "
        f"email_type, subject, resend_message_id, sequence_day, status, sent_at, created_at, updated_at) "
        f"VALUES ("
        f"'{log_id}', "
        f"'{outreach_id or ''}', "
        f"'{snapshot_id or ''}', "
        f"'{_esc(recipient_email)}', "
        f"'{email_type}', "
        f"'{_esc(subject)}', "
        f"'{resend_message_id}', "
        f"{sequence_day}, "
        f"'sent', "
        f"'{now}', "
        f"'{now}', "
        f"'{now}'"
        f")"
    )
    _run_team_db(sql)
    return log_id


def mark_snapshot_email_sent(snapshot_id: str, field: str) -> None:
    """Mark a timestamp field on the snapshot data."""
    update_snapshot_data(snapshot_id, field, _now_iso())


# ── Resend Sender ────────────────────────────────────────────────────────────

def _init_resend() -> None:
    if resend is None:
        raise RuntimeError("resend package not installed")
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY not configured")
    resend.api_key = RESEND_API_KEY


def _send(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    tags: Optional[list[dict[str, str]]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Internal send with optional dry-run."""
    if dry_run:
        logger.info(f"[DRY RUN] Would send to {to}: {subject}")
        return {"id": f"dryrun_{uuid.uuid4().hex[:12]}", "dry_run": True}

    _init_resend()
    params: dict[str, Any] = {
        "from": f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>",
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        params["text"] = text_body
    if tags:
        params["tags"] = tags

    response = resend.Emails.send(params)
    logger.info(f"Email sent to {to}: message_id={response.get('id')}")
    return response


# ── Public API ───────────────────────────────────────────────────────────────

def send_welcome(to_email: str, business_name: str, dry_run: bool = False) -> dict[str, Any]:
    """Send the immediate welcome/acknowledgment email after form submit."""
    html_body = render_welcome_email(business_name)
    text_body = f"""Hi there,

Thanks for requesting a Business Health Snapshot for {business_name}.
Our AI is analyzing your digital footprint right now.

Check your inbox in about 5 minutes for your personalized report.

LocalPulse AI
"""
    response = _send(
        to=to_email,
        subject=f"We're analyzing {business_name} — check your inbox in 5 minutes",
        html_body=html_body,
        text_body=text_body,
        tags=[{"name": "welcome", "value": "1"}],
        dry_run=dry_run,
    )
    return response


def send_snapshot_report(
    to_email: str,
    snapshot_data: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send the Business Health Snapshot as a beautiful HTML email.

    Also logs to email_logs and marks snapshot.report_sent_at.
    """
    snap_id = snapshot_data.get("id", "")
    html_body = render_snapshot_report(snapshot_data)

    data = snapshot_data.get("data", {}) or {}
    business_info = data.get("business_info", {})
    scoring = data.get("scoring_output", {})
    business_name = business_info.get("name", snapshot_data.get("business_name", "Your Business"))
    health_score = scoring.get("total_health_score", 0)

    text_body = f"""Your Business Health Snapshot for {business_name} is ready.

Health Score: {health_score}/100

View the full report: https://localpulse.ai

LocalPulse AI
"""
    subject = f"Your {business_name} Health Snapshot: {health_score}/100"
    response = _send(
        to=to_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        tags=[{"name": "snapshot_report", "value": snap_id}],
        dry_run=dry_run,
    )

    if not dry_run and snap_id:
        log_email(
            outreach_id=None,
            snapshot_id=snap_id,
            recipient_email=to_email,
            email_type="snapshot_report",
            subject=subject,
            resend_message_id=response.get("id", ""),
            sequence_day=0,
        )
        mark_snapshot_email_sent(snap_id, "report_sent_at")

    return response


def send_follow_up(
    to_email: str,
    snapshot_data: dict[str, Any],
    day: int,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send a drip follow-up email (day 1, 3, or 7).

    Logs to email_logs and marks the corresponding snapshot field.
    """
    snap_id = snapshot_data.get("id", "")
    subject, html_body = render_followup_email(snapshot_data, day)

    text_body = f"Follow-up regarding your Business Health Snapshot. Reply if you'd like to discuss.\n\nLocalPulse AI"
    response = _send(
        to=to_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        tags=[{"name": "followup", "value": str(day)}, {"name": "snapshot", "value": snap_id}],
        dry_run=dry_run,
    )

    if not dry_run and snap_id:
        log_email(
            outreach_id=None,
            snapshot_id=snap_id,
            recipient_email=to_email,
            email_type="follow_up",
            subject=subject,
            resend_message_id=response.get("id", ""),
            sequence_day=day,
        )
        field_map = {1: "follow_up_1_sent_at", 3: "follow_up_3_sent_at", 7: "follow_up_7_sent_at"}
        field = field_map.get(day)
        if field:
            mark_snapshot_email_sent(snap_id, field)

    return response


def send_upgrade_confirmation(
    to_email: str,
    tier: str,
    stripe_customer_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send the post-purchase welcome email with next steps."""
    html_body = render_upgrade_confirmation(tier, stripe_customer_id)
    tier_display = tier.title()
    text_body = f"""Welcome to LocalPulse {tier_display}!

Your subscription is confirmed. Here's what happens next:
1. Your first weekly snapshot arrives this Monday
2. Add competitors in your dashboard for benchmarking
3. Connect your Google Business Profile for real-time alerts

You have 30 days to claim your "Lead Leak" money-back guarantee.

LocalPulse AI
"""
    response = _send(
        to=to_email,
        subject=f"Welcome to LocalPulse {tier_display} — here's what happens next",
        html_body=html_body,
        text_body=text_body,
        tags=[{"name": "upgrade_confirmation", "value": tier}, {"name": "stripe_customer", "value": stripe_customer_id}],
        dry_run=dry_run,
    )
    return response


# ── Webhook Processing ───────────────────────────────────────────────────────

def process_resend_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Process a Resend webhook event (opened, clicked, bounced, etc.)."""
    event_type = payload.get("type", "")
    data = payload.get("data", {})
    message_id = data.get("email_id", "")

    if not message_id:
        return {"handled": False, "error": "missing email_id"}

    status_map = {
        "email.sent": "sent",
        "email.delivered": "delivered",
        "email.opened": "opened",
        "email.clicked": "clicked",
        "email.bounced": "bounced",
        "email.complained": "complained",
    }
    status = status_map.get(event_type)
    if not status:
        return {"handled": False, "type": event_type}

    ensure_email_log_table()
    now = _now_iso()
    col_map = {
        "opened": "opened_at",
        "clicked": "clicked_at",
        "bounced": "bounced_at",
    }
    col = col_map.get(status, "updated_at")
    _run_team_db(
        f"UPDATE email_logs SET status = '{status}', {col} = '{now}', updated_at = '{now}' "
        f"WHERE resend_message_id = '{message_id}'"
    )
    return {"handled": True, "type": event_type, "message_id": message_id}


# ── Sequence Runner ──────────────────────────────────────────────────────────

def get_pending_followups(day: int, max_results: int = 50) -> list[dict[str, Any]]:
    """Find snapshots ready for a specific follow-up day."""
    ensure_email_log_table()
    field_map = {1: "report_sent_at", 3: "follow_up_1_sent_at", 7: "follow_up_3_sent_at"}
    prev_field = field_map.get(day, "report_sent_at")
    target_field = f"follow_up_{day}_sent_at"

    # Fetch candidate snapshots and filter in Python (avoids SQLite JSON path issues)
    rows = _run_team_db(
        f"SELECT id, data FROM snapshots WHERE status IN ('completed', 'outreach_done', 'ready_for_outreach') "
        f"ORDER BY updated_at ASC LIMIT {max_results * 3}"
    )
    result = []
    for row in rows:
        data = row.get("data", {}) or {}
        if isinstance(data, str):
            try:
                import json
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue
        if data.get(prev_field) and not data.get(target_field) and data.get("requester_email"):
            row["data"] = data
            result.append(row)
        if len(result) >= max_results:
            break
    return result


def run_followup_sequences(day: int, max_sends: int = 10, dry_run: bool = False) -> int:
    """Send follow-up emails for all leads at the specified stage.

    Returns the number of emails sent.
    """
    pending = get_pending_followups(day, max_results=max_sends)
    sent = 0
    for row in pending:
        snap_id = row["id"]
        data = row.get("data", {}) or {}
        email = data.get("requester_email", "")
        if not email:
            continue

        try:
            send_follow_up(
                to_email=email,
                snapshot_data=row,
                day=day,
                dry_run=dry_run,
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Follow-up send failed for {snap_id}: {e}")

    return sent
