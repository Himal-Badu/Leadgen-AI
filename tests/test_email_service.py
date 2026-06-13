"""Tests for the Email Service and Report Renderer.

All Resend API calls are mocked — no real emails are sent.
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.report_renderer import (
    render_followup_email,
    render_snapshot_report,
    render_upgrade_confirmation,
    render_welcome_email,
    _score_color,
)

from core.email_service import (
    ensure_email_log_table,
    log_email,
    mark_snapshot_email_sent,
    process_resend_webhook,
    send_follow_up,
    send_snapshot_report,
    send_upgrade_confirmation,
    send_welcome,
    run_followup_sequences,
    get_pending_followups,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_email_logs():
    ensure_email_log_table()
    from core.database import _run_team_db
    _run_team_db("DELETE FROM email_logs WHERE recipient_email LIKE 'test_%'")
    yield


@pytest.fixture
def sample_snapshot():
    return {
        "id": "snap-test-123",
        "business_name": "Ace HVAC",
        "location": "Austin, TX",
        "status": "completed",
        "data": {
            "business_info": {"name": "Ace HVAC", "location": "Austin, TX"},
            "requester_email": "test_user@example.com",
            "scoring_output": {
                "total_health_score": 62,
                "pillars": {"visibility": 55, "trust": 70, "conversion": 60},
            },
            "analyzer_insights": {
                "gaps": [
                    "Google Business Profile missing primary category",
                    "No review response strategy",
                    "Mobile site loads in 6.2 seconds",
                ],
            },
            "growth_roadmap": [
                {"action": "Add primary GBP category", "details": "Set HVAC as primary", "impact": "High", "priority": 1},
                {"action": "Reply to recent reviews", "details": "Respond to all 3-star and below", "impact": "Medium", "priority": 2},
                {"action": "Compress images", "details": "Reduce mobile load time", "impact": "High", "priority": 3},
            ],
        },
    }


# ── Report Renderer Tests ────────────────────────────────────────────────────

def test_score_color():
    assert _score_color(85) == "#88c999"
    assert _score_color(70) == "#e8c96a"
    assert _score_color(45) == "#e07a7a"


def test_render_snapshot_report_contains_business_name(sample_snapshot):
    html = render_snapshot_report(sample_snapshot)
    assert "Ace HVAC" in html
    assert "Austin" in html
    assert "62" in html


def test_render_snapshot_report_contains_pillars(sample_snapshot):
    html = render_snapshot_report(sample_snapshot)
    assert "Visibility" in html
    assert "Trust" in html
    assert "Conversion" in html


def test_render_snapshot_report_contains_roadmap(sample_snapshot):
    html = render_snapshot_report(sample_snapshot)
    assert "Add primary GBP category" in html
    assert "Reply to recent reviews" in html
    assert "Compress images" in html


def test_render_welcome_email():
    html = render_welcome_email("Test Business")
    assert "Test Business" in html
    assert "We're On It" in html
    assert "5 minutes" in html


def test_render_followup_email_day1(sample_snapshot):
    subject, html = render_followup_email(sample_snapshot, day=1)
    assert "report is ready" in subject
    assert "Ace HVAC" in html
    assert "Google Business Profile missing primary category" in html


def test_render_followup_email_day3(sample_snapshot):
    subject, html = render_followup_email(sample_snapshot, day=3)
    assert "follow-up" in subject.lower()
    assert "Ace HVAC" in html


def test_render_followup_email_day7(sample_snapshot):
    subject, html = render_followup_email(sample_snapshot, day=7)
    assert "Last call" in subject
    assert "Ace HVAC" in html


def test_render_upgrade_confirmation_starter():
    html = render_upgrade_confirmation("starter", "cus_123")
    assert "Starter" in html
    assert "Weekly Health Snapshots" in html
    assert "30 days" in html


def test_render_upgrade_confirmation_pro():
    html = render_upgrade_confirmation("pro", "cus_123")
    assert "Pro" in html
    assert "Unlimited growth roadmaps" in html


def test_render_upgrade_confirmation_autopilot():
    html = render_upgrade_confirmation("autopilot", "cus_123")
    assert "Autopilot" in html
    assert "One-click publishing" in html


# ── Email Service Tests ──────────────────────────────────────────────────────

@patch("core.email_service._send")
def test_send_welcome(mock_send):
    mock_send.return_value = {"id": "msg_123"}
    response = send_welcome("test_welcome@example.com", "Test Biz")
    assert response["id"] == "msg_123"
    call_args = mock_send.call_args[1]
    assert call_args["to"] == "test_welcome@example.com"
    assert "Test Biz" in call_args["subject"]
    assert call_args["tags"] == [{"name": "welcome", "value": "1"}]


@patch("core.email_service._send")
def test_send_welcome_dry_run(mock_send):
    response = send_welcome("test_welcome@example.com", "Test Biz", dry_run=True)
    assert response["dry_run"] is True
    mock_send.assert_not_called()


@patch("core.email_service._send")
def test_send_snapshot_report(mock_send, sample_snapshot):
    mock_send.return_value = {"id": "msg_report"}
    response = send_snapshot_report("test_report@example.com", sample_snapshot)
    assert response["id"] == "msg_report"
    call_args = mock_send.call_args[1]
    assert call_args["to"] == "test_report@example.com"
    assert "Ace HVAC" in call_args["subject"]
    assert "62" in call_args["subject"]


@patch("core.email_service._send")
def test_send_snapshot_report_logs_to_db(mock_send, sample_snapshot):
    mock_send.return_value = {"id": "msg_log"}
    send_snapshot_report("test_log@example.com", sample_snapshot)
    from core.database import _run_team_db
    rows = _run_team_db("SELECT * FROM email_logs WHERE recipient_email = 'test_log@example.com'")
    assert len(rows) >= 1
    assert rows[0]["email_type"] == "snapshot_report"


@patch("core.email_service._send")
def test_send_follow_up_day1(mock_send, sample_snapshot):
    mock_send.return_value = {"id": "msg_fu1"}
    response = send_follow_up("test_fu@example.com", sample_snapshot, day=1)
    assert response["id"] == "msg_fu1"
    call_args = mock_send.call_args[1]
    assert call_args["to"] == "test_fu@example.com"
    assert call_args["tags"] == [{"name": "followup", "value": "1"}, {"name": "snapshot", "value": "snap-test-123"}]


@patch("core.email_service._send")
def test_send_follow_up_day3(mock_send, sample_snapshot):
    mock_send.return_value = {"id": "msg_fu3"}
    response = send_follow_up("test_fu3@example.com", sample_snapshot, day=3)
    assert response["id"] == "msg_fu3"


@patch("core.email_service._send")
def test_send_upgrade_confirmation(mock_send):
    mock_send.return_value = {"id": "msg_upg"}
    response = send_upgrade_confirmation("test_upg@example.com", "pro", "cus_123")
    assert response["id"] == "msg_upg"
    call_args = mock_send.call_args[1]
    assert call_args["to"] == "test_upg@example.com"
    assert "Pro" in call_args["subject"]


def test_process_resend_webhook_opened():
    payload = {"type": "email.opened", "data": {"email_id": "msg_abc"}}
    result = process_resend_webhook(payload)
    assert result["handled"] is True
    assert result["type"] == "email.opened"


def test_process_resend_webhook_bounced():
    payload = {"type": "email.bounced", "data": {"email_id": "msg_bounce"}}
    result = process_resend_webhook(payload)
    assert result["handled"] is True
    assert result["type"] == "email.bounced"


def test_process_resend_webhook_unhandled():
    payload = {"type": "email.delivered", "data": {"email_id": "msg_del"}}
    result = process_resend_webhook(payload)
    assert result["handled"] is True
    assert result["type"] == "email.delivered"


def test_process_resend_webhook_missing_id():
    payload = {"type": "email.opened", "data": {}}
    result = process_resend_webhook(payload)
    assert result["handled"] is False
    assert "missing email_id" in result["error"]


# ── Log & DB Tests ───────────────────────────────────────────────────────────

def test_log_email():
    log_id = log_email(
        outreach_id="out_123",
        snapshot_id="snap_123",
        recipient_email="test_db@example.com",
        email_type="snapshot_report",
        subject="Test Subject",
        resend_message_id="msg_123",
        sequence_day=0,
    )
    assert len(log_id) == 36
    from core.database import _run_team_db
    rows = _run_team_db("SELECT * FROM email_logs WHERE id = '{}'".format(log_id))
    assert len(rows) == 1
    assert rows[0]["status"] == "sent"


# ── Follow-up Sequence Tests ─────────────────────────────────────────────────

@patch("core.email_service.send_follow_up")
def test_run_followup_sequences(mock_send, sample_snapshot):
    mock_send.return_value = {"id": "msg_seq"}
    # Create a snapshot in DB with report_sent_at set but no follow_up_1_sent_at
    from core.database import create_snapshot, update_snapshot_data
    snap_id = create_snapshot(business_name="Seq Test", location="Dallas, TX")
    update_snapshot_data(snap_id, "requester_email", "test_seq@example.com")
    update_snapshot_data(snap_id, "report_sent_at", datetime.now(timezone.utc).isoformat())

    sent = run_followup_sequences(day=1, max_sends=5, dry_run=False)
    assert sent >= 1


def test_get_pending_followups_no_results():
    rows = get_pending_followups(day=7, max_results=10)
    assert isinstance(rows, list)
