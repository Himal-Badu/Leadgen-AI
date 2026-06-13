"""Email Delivery Integration for LocalPulse AI.

Uses Resend (https://resend.com) for transactional email delivery.
Supports HTML Business Health Snapshot reports, follow-up sequences,
and webhook tracking for opens/replies/bounces.

Environment:
    RESEND_API_KEY      — Resend API key
    EMAIL_FROM          — Verified sender address (default: alex@localpulse.ai)
    EMAIL_FROM_NAME     — Sender display name (default: Alex from LocalPulse)

Deliverability Best Practices (see DELIVERABILITY_GUIDE below):
    - SPF, DKIM, DMARC DNS records
    - Domain warm-up strategy
    - List hygiene and bounce handling
"""
import html
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    import resend
except ImportError:  # pragma: no cover
    resend = None

from core.database import _run_team_db

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "alex@localpulse.ai")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Alex from LocalPulse")

# ── Deliverability Guide ─────────────────────────────────────────────────────

DELIVERABILITY_GUIDE = """
═══════════════════════════════════════════════════════════════════════════════
LOCALPULSE AI — EMAIL DELIVERABILITY BEST PRACTICES
═══════════════════════════════════════════════════════════════════════════════

1. DNS RECORDS (Required before sending)
   ─────────────────────────────────────
   SPF (prevents spoofing):
     Type: TXT | Host: @ | Value: v=spf1 include:_spf.resend.com ~all

   DKIM (cryptographic signature):
     Resend auto-generates DKIM keys. Add the CNAME records they provide
     in your Resend dashboard under Domain Settings.

   DMARC (alignment + reporting):
     Type: TXT | Host: _dmarc | Value:
     v=DMARC1; p=quarantine; rua=mailto:dmarc@localpulse.ai; pct=100

2. DOMAIN WARM-UP (Critical for new domains)
   ──────────────────────────────────────────
   Week 1: 10–20 emails/day   to highly engaged recipients
   Week 2: 50–100 emails/day  gradually increase
   Week 3: 200–500 emails/day
   Week 4+: full volume

   Never blast a cold list. Start with your warmest contacts.

3. LIST HYGIENE
   ─────────────
   - Remove hard bounces immediately (Resend handles this automatically)
   - Remove recipients who haven't opened in 90+ days
   - Use double opt-in for new signups
   - Never purchase lists

4. CONTENT AVOIDANCE
   ──────────────────
   Avoid spam-trigger words/phrases in subject lines:
     "FREE", "Act Now", "$$$", "Urgent", "Limited Time"
   Keep image-to-text ratio low (< 30% images)
   Always include a plain-text fallback
   Include a clear unsubscribe link

5. MONITORING
   ───────────
   Track these metrics weekly:
     - Open rate target: > 20%
     - Click rate target: > 2%
     - Bounce rate ceiling: < 2%
     - Complaint rate ceiling: < 0.1%

   If any metric degrades, pause and warm up again before scaling.
═══════════════════════════════════════════════════════════════════════════════
"""


# ── Database ─────────────────────────────────────────────────────────────────

def _esc(value: str) -> str:
    return value.replace("'", "''")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_email_log_table() -> None:
    """Create the email_logs table for tracking sends, opens, bounces."""
    sql = """
    CREATE TABLE IF NOT EXISTS email_logs (
        id TEXT PRIMARY KEY,
        outreach_id TEXT,
        snapshot_id TEXT,
        recipient_email TEXT NOT NULL,
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


def log_email_send(
    outreach_id: str,
    snapshot_id: str,
    recipient_email: str,
    subject: str,
    resend_message_id: str,
    sequence_day: int = 0,
) -> str:
    """Log an email send to the database. Returns the log ID."""
    ensure_email_log_table()
    log_id = str(uuid.uuid4())
    now = _now_iso()
    sql = (
        f"INSERT INTO email_logs (id, outreach_id, snapshot_id, recipient_email, "
        f"subject, resend_message_id, sequence_day, status, sent_at, created_at, updated_at) "
        f"VALUES ("
        f"'{log_id}', "
        f"'{outreach_id}', "
        f"'{snapshot_id}', "
        f"'{_esc(recipient_email)}', "
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


def update_email_status(resend_message_id: str, status: str, timestamp: Optional[str] = None) -> None:
    """Update email status from webhook (opened, clicked, bounced, etc.)."""
    ensure_email_log_table()
    now = timestamp or _now_iso()
    col_map = {
        "opened": "opened_at",
        "clicked": "clicked_at",
        "bounced": "bounced_at",
        "delivered": "delivered_at",
    }
    col = col_map.get(status, "updated_at")
    _run_team_db(
        f"UPDATE email_logs SET status = '{status}', {col} = '{now}', updated_at = '{now}' "
        f"WHERE resend_message_id = '{resend_message_id}'"
    )


def get_email_logs_by_snapshot(snapshot_id: str) -> list[dict[str, Any]]:
    """Get all email logs for a snapshot."""
    ensure_email_log_table()
    return _run_team_db(
        f"SELECT * FROM email_logs WHERE snapshot_id = '{snapshot_id}' ORDER BY sequence_day ASC, created_at ASC"
    )


def get_pending_followups() -> list[dict[str, Any]]:
    """Get emails that need follow-up sequences sent."""
    ensure_email_log_table()
    # Find snapshots where the last email was sent > N days ago and no followup exists
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    rows = _run_team_db(
        f"SELECT * FROM email_logs WHERE status = 'sent' AND sequence_day = 0 "
        f"AND sent_at < '{cutoff}' AND snapshot_id NOT IN ("
        f"  SELECT snapshot_id FROM email_logs WHERE sequence_day > 0"
        f") ORDER BY sent_at ASC LIMIT 50"
    )
    return rows


# ── HTML Email Builder ───────────────────────────────────────────────────────

def build_snapshot_email(
    business_name: str,
    health_score: int,
    location: str,
    gaps: list[str],
    roadmap: list[dict[str, Any]],
    recipient_name: str = "there",
) -> str:
    """Build an HTML email containing the Business Health Snapshot report."""
    city = location.split(",")[0].strip() if "," in location else location

    # Gap list HTML
    gaps_html = ""
    for gap in gaps[:5]:
        gaps_html += f'<li style="margin-bottom:8px;color:#A8A29E;">{html.escape(gap)}</li>\n'

    # Roadmap HTML
    roadmap_html = ""
    for i, action in enumerate(roadmap[:3], 1):
        title = html.escape(action.get("action", "Action item"))
        desc = html.escape(action.get("details", ""))
        impact = html.escape(action.get("impact", "Medium"))
        roadmap_html += f"""
        <tr>
          <td style="padding:16px;border-bottom:1px solid rgba(235,220,196,0.15);">
            <div style="font-weight:700;color:#EBDCC4;margin-bottom:4px;">{i}. {title}</div>
            <div style="font-size:0.9rem;color:#A8A29E;margin-bottom:4px;">{desc}</div>
            <div style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.06em;color:#DC9F85;">Impact: {impact}</div>
          </td>
        </tr>
        """

    score_color = "#DC9F85" if health_score < 60 else "#EBDCC4" if health_score < 80 else "#88c999"

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#181818;font-family:'Inter',system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#181818;">
    <tr><td align="center" style="padding:40px 20px;">
      <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;border:1px solid rgba(235,220,196,0.15);border-radius:4px;overflow:hidden;">
        <!-- Header -->
        <tr><td style="padding:40px 32px 24px;border-bottom:1px solid rgba(235,220,196,0.15);">
          <div style="font-family:'Inter',system-ui,sans-serif;font-weight:800;font-size:1.25rem;color:#EBDCC4;letter-spacing:-0.03em;">LocalPulse<span style="color:#DC9F85;">.</span>AI</div>
        </td></tr>
        <!-- Hero -->
        <tr><td style="padding:32px;">
          <h1 style="font-family:'Inter',system-ui,sans-serif;font-size:1.75rem;font-weight:700;color:#EBDCC4;line-height:1.2;margin:0 0 16px;">Your Business Health Snapshot is Ready</h1>
          <p style="font-size:1rem;color:#A8A29E;line-height:1.6;margin:0 0 24px;">Hi {html.escape(recipient_name)},</p>
          <p style="font-size:1rem;color:#A8A29E;line-height:1.6;margin:0 0 24px;">I just finished analyzing <strong style="color:#EBDCC4;">{html.escape(business_name)}</strong> in {html.escape(city)}. Here are the results:</p>
          <!-- Score Card -->
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid rgba(235,220,196,0.15);border-radius:4px;margin-bottom:24px;">
            <tr><td style="padding:24px;text-align:center;">
              <div style="font-size:3rem;font-weight:700;color:{score_color};line-height:1;">{health_score}</div>
              <div style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.08em;color:#A8A29E;margin-top:8px;">Health Score / 100</div>
            </td></tr>
          </table>
          <!-- Gaps -->
          <h2 style="font-size:1.1rem;font-weight:700;color:#EBDCC4;text-transform:uppercase;letter-spacing:0.04em;margin:0 0 16px;">Top Gaps</h2>
          <ul style="padding-left:20px;margin:0 0 24px;">
            {gaps_html}
          </ul>
          <!-- Roadmap -->
          <h2 style="font-size:1.1rem;font-weight:700;color:#EBDCC4;text-transform:uppercase;letter-spacing:0.04em;margin:0 0 16px;">Your 3-Step Fix-It Roadmap</h2>
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            {roadmap_html}
          </table>
        </td></tr>
        <!-- CTA -->
        <tr><td style="padding:0 32px 32px;text-align:center;">
          <a href="https://localpulse.ai" style="display:inline-block;font-weight:600;font-size:0.9rem;text-transform:uppercase;letter-spacing:0.05em;padding:16px 32px;border-radius:4px;background-color:#DC9F85;color:#181818;text-decoration:none;">View Full Report</a>
        </td></tr>
        <!-- Footer -->
        <tr><td style="padding:24px 32px;border-top:1px solid rgba(235,220,196,0.15);text-align:center;">
          <p style="font-size:0.8rem;color:#A8A29E;margin:0;">LocalPulse AI — Business Intelligence for Local Service Companies</p>
          <p style="font-size:0.75rem;color:#A8A29E;margin:8px 0 0;">
            <a href="{{unsubscribe_url}}" style="color:#A8A29E;text-decoration:underline;">Unsubscribe</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_followup_email(
    business_name: str,
    day: int,
    recipient_name: str = "there",
) -> tuple[str, str]:
    """Build a follow-up email subject and HTML body.

    Returns (subject, html_body).
    """
    subjects = {
        3: f"Quick follow-up: your {business_name} roadmap",
        7: f"Last call: {business_name} lead leak fix",
        14: f"Still losing leads in {business_name}?",
    }
    subject = subjects.get(day, f"Follow-up: {business_name} Health Snapshot")

    bodies = {
        3: f"""<p>Hi {html.escape(recipient_name)},</p>
<p>I wanted to follow up on the Business Health Snapshot I sent for <strong>{html.escape(business_name)}</strong> a few days ago.</p>
<p>The top fix I identified typically increases local leads by 20–40% within the first month. Most business owners implement it in under an hour.</p>
<p>If you'd like me to walk you through it on a quick 10-minute call, just reply to this email.</p>
<p>Best,<br>Alex<br>LocalPulse AI</p>""",
        7: f"""<p>Hi {html.escape(recipient_name)},</p>
<p>I know you're busy running <strong>{html.escape(business_name)}</strong>, so I'll keep this short.</p>
<p>The gap I found in your local presence is likely costing you calls every week. The good news: it's a one-time fix with lasting impact.</p>
<p>I'm closing my calendar for new onboarding calls at the end of the week. If you want to grab a slot, just reply and I'll send over a few times.</p>
<p>Best,<br>Alex<br>LocalPulse AI</p>""",
        14: f"""<p>Hi {html.escape(recipient_name)},</p>
<p>I ran another quick scan on <strong>{html.escape(business_name)}</strong> and the gap is still open — which means your competitors are still picking up the leads you're missing.</p>
<p>If you've already fixed it, great — just ignore this. If not, I'm happy to send over the exact step-by-step instructions, no call needed.</p>
<p>Just reply "SEND IT" and I'll fire them over.</p>
<p>Best,<br>Alex<br>LocalPulse AI</p>""",
    }
    body_html = bodies.get(day, bodies[3])

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background-color:#181818;font-family:'Inter',system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#181818;">
    <tr><td align="center" style="padding:40px 20px;">
      <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;border:1px solid rgba(235,220,196,0.15);border-radius:4px;overflow:hidden;">
        <tr><td style="padding:40px 32px 24px;border-bottom:1px solid rgba(235,220,196,0.15);">
          <div style="font-weight:800;font-size:1.25rem;color:#EBDCC4;letter-spacing:-0.03em;">LocalPulse<span style="color:#DC9F85;">.</span>AI</div>
        </td></tr>
        <tr><td style="padding:32px;font-size:1rem;color:#A8A29E;line-height:1.6;">
          {body_html}
        </td></tr>
        <tr><td style="padding:24px 32px;border-top:1px solid rgba(235,220,196,0.15);text-align:center;">
          <p style="font-size:0.8rem;color:#A8A29E;margin:0;">LocalPulse AI</p>
          <p style="font-size:0.75rem;color:#A8A29E;margin:8px 0 0;"><a href="{{unsubscribe_url}}" style="color:#A8A29E;text-decoration:underline;">Unsubscribe</a></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return subject, html_body


# ── Resend Sender ────────────────────────────────────────────────────────────

def _init_resend() -> None:
    """Initialize Resend with API key."""
    if resend is None:
        raise RuntimeError("resend package not installed")
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY not configured")
    resend.api_key = RESEND_API_KEY


def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    tags: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """Send an email via Resend.

    Returns the Resend API response dict with 'id' (message_id).
    """
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


def send_snapshot_report(
    to: str,
    business_name: str,
    health_score: int,
    location: str,
    gaps: list[str],
    roadmap: list[dict[str, Any]],
    outreach_id: str,
    snapshot_id: str,
    recipient_name: str = "there",
) -> dict[str, Any]:
    """Send the Business Health Snapshot as an HTML email.

    Logs the send to the database and returns the Resend response.
    """
    html_body = build_snapshot_email(
        business_name=business_name,
        health_score=health_score,
        location=location,
        gaps=gaps,
        roadmap=roadmap,
        recipient_name=recipient_name,
    )
    text_body = f"""Hi {recipient_name},

Your Business Health Snapshot for {business_name} in {location} is ready.

Health Score: {health_score}/100

Top Gaps:
{chr(10).join(f"- {g}" for g in gaps[:5])}

View the full report: https://localpulse.ai

LocalPulse AI
"""
    response = send_email(
        to=to,
        subject=f"Your {business_name} Health Snapshot: {health_score}/100",
        html_body=html_body,
        text_body=text_body,
        tags=[{"name": "snapshot_report", "value": snapshot_id}],
    )
    message_id = response.get("id", "")
    log_email_send(
        outreach_id=outreach_id,
        snapshot_id=snapshot_id,
        recipient_email=to,
        subject=f"Your {business_name} Health Snapshot: {health_score}/100",
        resend_message_id=message_id,
        sequence_day=0,
    )
    return response


def send_followup_email(
    to: str,
    business_name: str,
    day: int,
    outreach_id: str,
    snapshot_id: str,
    recipient_name: str = "there",
) -> dict[str, Any]:
    """Send a follow-up email in the sequence.

    Days: 3, 7, 14 (after initial send).
    """
    subject, html_body = build_followup_email(
        business_name=business_name,
        day=day,
        recipient_name=recipient_name,
    )
    text_body = f"Hi {recipient_name},\n\nThis is a follow-up regarding the Business Health Snapshot for {business_name}.\n\nBest,\nAlex\nLocalPulse AI"
    response = send_email(
        to=to,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        tags=[{"name": "followup", "value": str(day)}, {"name": "snapshot", "value": snapshot_id}],
    )
    message_id = response.get("id", "")
    log_email_send(
        outreach_id=outreach_id,
        snapshot_id=snapshot_id,
        recipient_email=to,
        subject=subject,
        resend_message_id=message_id,
        sequence_day=day,
    )
    return response


# ── Webhook Processing ───────────────────────────────────────────────────────

def process_resend_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Process a Resend webhook event.

    Resend webhooks send events like: email.sent, email.delivered,
    email.opened, email.clicked, email.bounced, email.complained.
    """
    event_type = payload.get("type", "")
    data = payload.get("data", {})
    message_id = data.get("email_id", "")

    if not message_id:
        logger.warning("Webhook missing email_id")
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
        logger.info(f"Unhandled Resend webhook type: {event_type}")
        return {"handled": False, "type": event_type}

    update_email_status(message_id, status)
    logger.info(f"Resend webhook processed: {event_type} for {message_id}")
    return {"handled": True, "type": event_type, "message_id": message_id}


# ── Sequence Runner ──────────────────────────────────────────────────────────

def run_followup_sequences(max_sends: int = 10) -> int:
    """Check for pending follow-ups and send them.

    Returns the number of follow-ups sent.
    """
    pending = get_pending_followups()
    sent = 0
    for log in pending[:max_sends]:
        snapshot_id = log["snapshot_id"]
        # We need recipient info — look it up from the snapshot
        from core.database import get_snapshot
        snapshot = get_snapshot(snapshot_id)
        if not snapshot:
            continue
        data = snapshot.get("data", {}) or {}
        email = data.get("requester_email", "")
        if not email:
            continue
        business_info = data.get("business_info", {})
        business_name = business_info.get("name", snapshot["business_name"])

        # Determine which follow-up day to send
        # (In a real system you'd track this more carefully)
        days = [3, 7, 14]
        # For simplicity, send day 3 if none sent yet
        day = 3

        try:
            send_followup_email(
                to=email,
                business_name=business_name,
                day=day,
                outreach_id=log["outreach_id"],
                snapshot_id=snapshot_id,
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Follow-up send failed for {snapshot_id}: {e}")

    return sent
