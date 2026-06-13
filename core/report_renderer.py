"""Report Renderer — Converts snapshot JSON into beautiful HTML emails.

Matches the LocalPulse editorial aesthetic: dark matte palette,
clean typography, and premium feel. All emails are mobile-responsive.
"""
import html
from typing import Any

# ── Design Tokens ────────────────────────────────────────────────────────────

COLORS = {
    "bg": "#181818",
    "text": "#EBDCC4",
    "accent": "#DC9F85",
    "muted": "#A8A29E",
    "border": "rgba(235, 220, 196, 0.15)",
    "green": "#88c999",
    "yellow": "#e8c96a",
    "red": "#e07a7a",
}


def _esc(text: str) -> str:
    return html.escape(str(text))


def _score_color(score: int) -> str:
    if score >= 80:
        return COLORS["green"]
    if score >= 60:
        return COLORS["yellow"]
    return COLORS["red"]


def _pillars_from_scoring(scoring: dict[str, Any]) -> dict[str, int]:
    """Extract pillar scores from scoring output."""
    pillars = scoring.get("pillars", {})
    return {
        "visibility": pillars.get("visibility", 0),
        "trust": pillars.get("trust", 0),
        "conversion": pillars.get("conversion", 0),
    }


def render_snapshot_report(snapshot_data: dict[str, Any]) -> str:
    """Render a full Business Health Snapshot as HTML email."""
    data = snapshot_data.get("data", {}) or {}
    business_info = data.get("business_info", {})
    scoring = data.get("scoring_output", {})
    insights = data.get("analyzer_insights", {})
    roadmap = data.get("growth_roadmap", [])
    deliverables = data.get("draft_deliverables", {})

    business_name = business_info.get("name", snapshot_data.get("business_name", "Your Business"))
    location = business_info.get("location", snapshot_data.get("location", ""))
    city = location.split(",")[0].strip() if "," in location else location

    health_score = scoring.get("total_health_score", 0)
    pillars = _pillars_from_scoring(scoring)
    gaps = insights.get("gaps", [])

    # Health score visual
    score_hex = _score_color(health_score)

    # Pillar bars
    pillar_bars = ""
    for name, score in pillars.items():
        bar_color = _score_color(score)
        pillar_bars += f"""
        <tr>
          <td style="padding:8px 0;font-size:0.9rem;color:{COLORS['muted']};text-transform:uppercase;letter-spacing:0.06em;">{name.title()}</td>
          <td style="padding:8px 0;width:60%;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="background:{COLORS['border']};border-radius:2px;height:8px;">
                  <div style="width:{score}%;background:{bar_color};height:8px;border-radius:2px;"></div>
                </td>
              </tr>
            </table>
          </td>
          <td style="padding:8px 0;text-align:right;font-weight:700;color:{bar_color};width:40px;">{score}</td>
        </tr>
        """

    # Gaps
    gaps_html = ""
    for gap in gaps[:5]:
        gaps_html += f'<li style="margin-bottom:10px;color:{COLORS["muted"]};line-height:1.5;">{_esc(gap)}</li>\n'

    # Roadmap
    roadmap_html = ""
    for i, action in enumerate(roadmap[:3], 1):
        title = _esc(action.get("action", "Action"))
        desc = _esc(action.get("details", ""))
        impact = _esc(action.get("impact", "Medium"))
        priority = action.get("priority", i)
        roadmap_html += f"""
        <tr>
          <td style="padding:20px;border-bottom:1px solid {COLORS['border']};vertical-align:top;">
            <div style="font-family:'Inter',system-ui,sans-serif;font-weight:700;font-size:1.5rem;color:{COLORS['accent']};line-height:1;margin-bottom:12px;">0{priority}</div>
            <div style="font-weight:700;color:{COLORS['text']};margin-bottom:6px;">{title}</div>
            <div style="font-size:0.9rem;color:{COLORS['muted']};margin-bottom:8px;line-height:1.5;">{desc}</div>
            <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:{COLORS['accent']};">Impact: {impact}</div>
          </td>
        </tr>
        """

    # Deliverables preview (if available)
    deliverables_html = ""
    if deliverables:
        items = []
        if deliverables.get("review_reply_drafts"):
            items.append("AI-generated review reply drafts")
        if deliverables.get("seo_meta_description"):
            items.append("SEO meta description rewrite")
        if deliverables.get("gbp_description"):
            items.append("Google Business Profile description")
        if deliverables.get("cta_copy"):
            items.append("High-conversion CTA copy")
        if deliverables.get("landing_page_headlines"):
            items.append("Landing page headline suggestions")
        if items:
            deliverables_html = f"""
            <tr><td style="padding:32px;border-top:1px solid {COLORS['border']};">
              <h2 style="font-size:1.1rem;font-weight:700;color:{COLORS['text']};text-transform:uppercase;letter-spacing:0.04em;margin:0 0 16px;">Bonus: Ready-to-Use Copy Drafts</h2>
              <ul style="padding-left:20px;margin:0;">
                {''.join(f'<li style="margin-bottom:8px;color:{COLORS["muted"]};">{_esc(item)}</li>' for item in items)}
              </ul>
            </td></tr>
            """

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:{COLORS['bg']};font-family:'Inter',system-ui,sans-serif;-webkit-font-smoothing:antialiased;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{COLORS['bg']};">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;border:1px solid {COLORS['border']};border-radius:4px;overflow:hidden;">
        <!-- Header -->
        <tr><td style="padding:32px 28px 20px;border-bottom:1px solid {COLORS['border']};">
          <div style="font-weight:800;font-size:1.25rem;color:{COLORS['text']};letter-spacing:-0.03em;">LocalPulse<span style="color:{COLORS['accent']};">.</span>AI</div>
        </td></tr>
        <!-- Intro -->
        <tr><td style="padding:28px;">
          <h1 style="font-size:1.6rem;font-weight:700;color:{COLORS['text']};line-height:1.2;margin:0 0 12px;">Your Business Health Snapshot</h1>
          <p style="font-size:1rem;color:{COLORS['muted']};line-height:1.6;margin:0;">{_esc(business_name)} in {_esc(city)}</p>
        </td></tr>
        <!-- Score Card -->
        <tr><td style="padding:0 28px 28px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid {COLORS['border']};border-radius:4px;">
            <tr><td style="padding:32px;text-align:center;">
              <div style="font-size:4rem;font-weight:700;color:{score_hex};line-height:1;">{health_score}</div>
              <div style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.08em;color:{COLORS['muted']};margin-top:8px;">Health Score / 100</div>
            </td></tr>
          </table>
        </td></tr>
        <!-- Pillar Breakdown -->
        <tr><td style="padding:0 28px 28px;">
          <h2 style="font-size:1rem;font-weight:700;color:{COLORS['text']};text-transform:uppercase;letter-spacing:0.04em;margin:0 0 16px;">Score Breakdown</h2>
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            {pillar_bars}
          </table>
        </td></tr>
        <!-- Gaps -->
        <tr><td style="padding:0 28px 28px;">
          <h2 style="font-size:1rem;font-weight:700;color:{COLORS['text']};text-transform:uppercase;letter-spacing:0.04em;margin:0 0 16px;">Top Gaps</h2>
          <ul style="padding-left:20px;margin:0;">
            {gaps_html}
          </ul>
        </td></tr>
        <!-- Roadmap -->
        <tr><td style="padding:0 28px;">
          <h2 style="font-size:1rem;font-weight:700;color:{COLORS['text']};text-transform:uppercase;letter-spacing:0.04em;margin:0 0 16px;">3-Step Growth Roadmap</h2>
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            {roadmap_html}
          </table>
        </td></tr>
        {deliverables_html}
        <!-- CTA -->
        <tr><td style="padding:28px;text-align:center;border-top:1px solid {COLORS['border']};">
          <a href="https://localpulse.ai#pricing" style="display:inline-block;font-weight:600;font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em;padding:16px 32px;border-radius:4px;background-color:{COLORS['accent']};color:{COLORS['bg']};text-decoration:none;">Put Growth on Autopilot</a>
          <p style="font-size:0.8rem;color:{COLORS['muted']};margin-top:12px;">Upgrade to LocalPulse Pro for unlimited roadmaps and AI review replies.</p>
        </td></tr>
        <!-- Footer -->
        <tr><td style="padding:20px 28px;border-top:1px solid {COLORS['border']};text-align:center;">
          <p style="font-size:0.75rem;color:{COLORS['muted']};margin:0;">LocalPulse AI — Business Intelligence for Local Service Companies</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def render_welcome_email(business_name: str) -> str:
    """Render the welcome/acknowledgment email."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background-color:{COLORS['bg']};font-family:'Inter',system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{COLORS['bg']};">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;border:1px solid {COLORS['border']};border-radius:4px;overflow:hidden;">
        <tr><td style="padding:32px 28px 20px;border-bottom:1px solid {COLORS['border']};">
          <div style="font-weight:800;font-size:1.25rem;color:{COLORS['text']};letter-spacing:-0.03em;">LocalPulse<span style="color:{COLORS['accent']};">.</span>AI</div>
        </td></tr>
        <tr><td style="padding:28px;">
          <h1 style="font-size:1.4rem;font-weight:700;color:{COLORS['text']};line-height:1.2;margin:0 0 16px;">We're On It.</h1>
          <p style="font-size:1rem;color:{COLORS['muted']};line-height:1.6;margin:0 0 16px;">Hi there,</p>
          <p style="font-size:1rem;color:{COLORS['muted']};line-height:1.6;margin:0 0 16px;">Thanks for requesting a Business Health Snapshot for <strong style="color:{COLORS['text']};">{_esc(business_name)}</strong>. Our AI is analyzing your digital footprint right now.</p>
          <p style="font-size:1rem;color:{COLORS['muted']};line-height:1.6;margin:0 0 24px;">Check your inbox in about <strong style="color:{COLORS['text']};">5 minutes</strong> for your personalized report.</p>
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid {COLORS['border']};border-radius:4px;">
            <tr><td style="padding:20px;">
              <p style="font-size:0.9rem;color:{COLORS['muted']};margin:0;line-height:1.5;">While you wait, here's what we'll check:</p>
              <ul style="padding-left:20px;margin:8px 0 0;">
                <li style="margin-bottom:6px;color:{COLORS['muted']};font-size:0.9rem;">Google Business Profile completeness</li>
                <li style="margin-bottom:6px;color:{COLORS['muted']};font-size:0.9rem;">Review volume, rating &amp; response rate</li>
                <li style="margin-bottom:6px;color:{COLORS['muted']};font-size:0.9rem;">Website speed &amp; mobile experience</li>
                <li style="margin-bottom:0;color:{COLORS['muted']};font-size:0.9rem;">Booking flow &amp; CTA visibility</li>
              </ul>
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:20px 28px;border-top:1px solid {COLORS['border']};text-align:center;">
          <p style="font-size:0.75rem;color:{COLORS['muted']};margin:0;">LocalPulse AI</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def render_followup_email(snapshot_data: dict[str, Any], day: int) -> tuple[str, str]:
    """Render a follow-up drip email. Returns (subject, html_body)."""
    data = snapshot_data.get("data", {}) or {}
    business_info = data.get("business_info", {})
    insights = data.get("analyzer_insights", {})
    business_name = business_info.get("name", snapshot_data.get("business_name", "Your Business"))
    gaps = insights.get("gaps", [])
    top_gap = gaps[0] if gaps else "your Google Business Profile is incomplete"

    subjects = {
        1: f"Your {business_name} report is ready — here's the #1 fix",
        3: f"Quick follow-up: your {business_name} roadmap",
        7: f"Last call: {business_name} lead leak fix",
    }
    subject = subjects.get(day, f"Follow-up: {business_name} Health Snapshot")

    bodies = {
        1: f"""<p>Your Business Health Snapshot for <strong>{_esc(business_name)}</strong> is ready.</p>
<p>The #1 gap we found: <strong style="color:{COLORS['accent']};">{_esc(top_gap)}</strong>. This is likely costing you leads every week.</p>
<p>We've also prepared a 3-step roadmap to fix it. Most business owners see results within the first month.</p>
<p><a href="https://localpulse.ai#pricing" style="color:{COLORS['accent']};text-decoration:underline;">Upgrade to Pro</a> to unlock unlimited roadmaps and AI-generated review replies.</p>""",
        3: f"""<p>Hi there,</p>
<p>I wanted to follow up on the Business Health Snapshot I sent for <strong>{_esc(business_name)}</strong> a few days ago.</p>
<p>The top fix we identified — <strong style="color:{COLORS['accent']};">{_esc(top_gap)}</strong> — typically increases local leads by 20–40% within the first month. Most business owners implement it in under an hour.</p>
<p>If you'd like me to walk you through it on a quick 10-minute call, just reply to this email.</p>""",
        7: f"""<p>Hi there,</p>
<p>I know you're busy running <strong>{_esc(business_name)}</strong>, so I'll keep this short.</p>
<p>The gap we found in your local presence — <strong style="color:{COLORS['accent']};">{_esc(top_gap)}</strong> — is likely costing you calls every week. The good news: it's a one-time fix with lasting impact.</p>
<p>I'm closing my calendar for new onboarding calls at the end of the week. If you want to grab a slot, just reply and I'll send over a few times.</p>""",
    }
    body = bodies.get(day, bodies[1])

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background-color:{COLORS['bg']};font-family:'Inter',system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{COLORS['bg']};">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;border:1px solid {COLORS['border']};border-radius:4px;overflow:hidden;">
        <tr><td style="padding:32px 28px 20px;border-bottom:1px solid {COLORS['border']};">
          <div style="font-weight:800;font-size:1.25rem;color:{COLORS['text']};letter-spacing:-0.03em;">LocalPulse<span style="color:{COLORS['accent']};">.</span>AI</div>
        </td></tr>
        <tr><td style="padding:28px;font-size:1rem;color:{COLORS['muted']};line-height:1.6;">
          {body}
          <p style="margin-top:24px;">Best,<br>Alex<br>LocalPulse AI</p>
        </td></tr>
        <tr><td style="padding:20px 28px;border-top:1px solid {COLORS['border']};text-align:center;">
          <p style="font-size:0.75rem;color:{COLORS['muted']};margin:0;">LocalPulse AI</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return subject, html_body


def render_upgrade_confirmation(tier: str, stripe_customer_id: str) -> str:
    """Render the post-purchase welcome email."""
    tier_names = {"starter": "Starter", "pro": "Pro", "autopilot": "Autopilot"}
    tier_display = tier_names.get(tier, tier.title())

    features = {
        "starter": [
            "Weekly Health Snapshots every Monday",
            "Competitor move alerts",
            "Review monitoring dashboard",
            "3 prioritized fixes per month",
        ],
        "pro": [
            "Everything in Starter",
            "Deep competitor benchmarking",
            "Unlimited growth roadmaps",
            "Local search rank tracker",
            "AI review reply generator",
        ],
        "autopilot": [
            "Everything in Pro",
            "Done-for-you AI drafts",
            "One-click publishing",
            "Monthly conversion audits",
            "Priority support",
        ],
    }
    feature_list = features.get(tier, features["starter"])
    features_html = "".join(
        f'<li style="margin-bottom:8px;color:{COLORS["muted"]};">{_esc(f)}</li>'
        for f in feature_list
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background-color:{COLORS['bg']};font-family:'Inter',system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{COLORS['bg']};">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;border:1px solid {COLORS['border']};border-radius:4px;overflow:hidden;">
        <tr><td style="padding:32px 28px 20px;border-bottom:1px solid {COLORS['border']};">
          <div style="font-weight:800;font-size:1.25rem;color:{COLORS['text']};letter-spacing:-0.03em;">LocalPulse<span style="color:{COLORS['accent']};">.</span>AI</div>
        </td></tr>
        <tr><td style="padding:28px;">
          <h1 style="font-size:1.4rem;font-weight:700;color:{COLORS['text']};line-height:1.2;margin:0 0 16px;">Welcome to LocalPulse {tier_display}.</h1>
          <p style="font-size:1rem;color:{COLORS['muted']};line-height:1.6;margin:0 0 16px;">Your subscription is confirmed and your account is being set up right now.</p>
          <p style="font-size:1rem;color:{COLORS['muted']};line-height:1.6;margin:0 0 24px;">Here's what you get with {tier_display}:</p>
          <ul style="padding-left:20px;margin:0 0 24px;">
            {features_html}
          </ul>
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid {COLORS['border']};border-radius:4px;">
            <tr><td style="padding:20px;">
              <p style="font-size:0.9rem;color:{COLORS['muted']};margin:0;line-height:1.5;"><strong style="color:{COLORS['text']};">Next steps:</strong></p>
              <ol style="padding-left:20px;margin:8px 0 0;">
                <li style="margin-bottom:6px;color:{COLORS['muted']};font-size:0.9rem;">Your first weekly snapshot arrives this Monday</li>
                <li style="margin-bottom:6px;color:{COLORS['muted']};font-size:0.9rem;">Add your competitors in the dashboard for benchmarking</li>
                <li style="margin-bottom:0;color:{COLORS['muted']};font-size:0.9rem;">Connect your Google Business Profile for real-time alerts</li>
              </ol>
            </td></tr>
          </table>
          <p style="font-size:0.9rem;color:{COLORS['muted']};margin:16px 0 0;line-height:1.5;">Remember: you have <strong style="color:{COLORS['accent']};">30 days</strong> to claim your "Lead Leak" money-back guarantee. If we don't find at least one critical issue you can fix, we'll refund your first month in full.</p>
        </td></tr>
        <tr><td style="padding:20px 28px;border-top:1px solid {COLORS['border']};text-align:center;">
          <p style="font-size:0.75rem;color:{COLORS['muted']};margin:0;">LocalPulse AI — Questions? Reply to this email.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
