import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SENDER_EMAIL  = os.getenv("SES_SENDER_EMAIL", "")
AWS_REGION    = os.getenv("AWS_REGION", "us-east-1")

# SMTP fallback — works with Gmail, SendGrid, Mailhog, etc.
SMTP_HOST     = os.getenv("SMTP_HOST", "")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


def _send(to: str, subject: str, html: str) -> None:
    if not to:
        print("[EMAIL SKIP] No recipient address — configure driver_email on the ride")
        return

    # ── Option 1: SMTP (Gmail / SendGrid / Mailhog for local dev) ──
    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = SENDER_EMAIL or SMTP_USER
            msg["To"]      = to
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(msg["From"], [to], msg.as_string())
            print(f"[EMAIL SENT via SMTP] To: {to} | {subject}")
            return
        except Exception as e:
            print(f"[EMAIL ERROR SMTP] {e}")

    # ── Option 2: AWS SES ───────────────────────────────────────────
    if SENDER_EMAIL:
        try:
            import boto3
            from botocore.exceptions import ClientError
            boto3.client("ses", region_name=AWS_REGION).send_email(
                Source=SENDER_EMAIL,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": subject},
                    "Body":    {"Html": {"Data": html}},
                },
            )
            print(f"[EMAIL SENT via SES] To: {to} | {subject}")
            return
        except ClientError as e:
            print(f"[EMAIL ERROR SES] {e.response['Error']['Message']}")

    # ── Fallback: console mock ──────────────────────────────────────
    print("[EMAIL MOCK] Set SMTP_HOST+SMTP_USER+SMTP_PASSWORD or SES_SENDER_EMAIL to send real emails")
    print(f"  ► To:      {to}")
    print(f"  ► Subject: {subject}")


# Same mark as the site favicon/nav logo — steering wheel + 3 warm stage-light
# beams. Kept as a literal inline <svg> (not a data-URI <img>, which Gmail's
# image proxy and most clients strip for security) so it renders natively in
# Gmail, Apple Mail and mobile clients. Outlook's desktop Word-based renderer
# doesn't support SVG and will simply skip it — acceptable degradation for a
# festival-audience product where that client is effectively unused.
_LOGO_SVG = """
<svg width="30" height="30" viewBox="0 0 24 24" fill="none" style="vertical-align:middle;">
  <polygon points="12,11 4.2,0.9 6.6,0.2" fill="#ffe066"/>
  <polygon points="12,11 10.9,0 13.1,0" fill="#ff6a00"/>
  <polygon points="12,11 17.4,0.2 19.8,0.9" fill="#ffb238"/>
  <circle cx="12" cy="12" r="9" fill="none" stroke="#f5f5f5" stroke-width="1.6"/>
  <line x1="4.1" y1="12" x2="9.8" y2="12" stroke="#f5f5f5" stroke-width="1.3" stroke-linecap="round"/>
  <line x1="14.2" y1="12" x2="19.9" y2="12" stroke="#f5f5f5" stroke-width="1.3" stroke-linecap="round"/>
  <line x1="12" y1="14.2" x2="12" y2="19.9" stroke="#f5f5f5" stroke-width="1.3" stroke-linecap="round"/>
  <circle cx="12" cy="12" r="2.6" fill="#ff3300"/>
</svg>
"""

_ICON_PIN = """
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FF3300" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;">
  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
</svg>
"""

_ICON_CLOCK = """
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FF3300" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;">
  <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
</svg>
"""


def _wrap_email(title: str, body_html: str) -> str:
    """Shared branded shell — dark card, fire/gold accent bar, real site logo.
    Table-based layout and inline styles throughout for email-client safety
    (no external stylesheet, no flexbox/grid, no CSS animation)."""
    return f"""
    <div dir="rtl" style="font-family:Arial,Helvetica,sans-serif;background:#050505;padding:32px 16px;">
      <table role="presentation" width="100%" style="max-width:480px;margin:0 auto;border-collapse:collapse;">
        <tr>
          <td style="height:4px;line-height:4px;font-size:0;background:linear-gradient(90deg,#FFE066,#FF6A00,#FF3300,#FFB238);border-radius:14px 14px 0 0;">&nbsp;</td>
        </tr>
        <tr>
          <td style="background:#0A0A0A;border:1px solid #252525;border-top:none;border-radius:0 0 14px 14px;padding:28px 26px;">

            <table role="presentation" style="margin-bottom:22px;">
              <tr>
                <td style="padding-left:9px;">{_LOGO_SVG}</td>
                <td style="font-size:21px;font-weight:900;color:#F5F5F5;letter-spacing:-.02em;">FastiRide</td>
              </tr>
            </table>

            <h2 style="color:#FF7A33;margin:0 0 14px;font-size:18px;font-weight:800;">{title}</h2>

            {body_html}

          </td>
        </tr>
        <tr>
          <td style="text-align:center;padding-top:18px;">
            <span style="font-size:11px;color:#3a3a3a;">FastiRide · פלטפורמת שיתוף נסיעות לפסטיבלים ומסיבות</span>
          </td>
        </tr>
      </table>
    </div>
    """


def send_join_notification(
    driver_email: str,
    driver_name: str,
    passenger_name: str,
    ride_city: str,
    departure_time: str,
) -> None:
    body = f"""
    <p style="color:#94a3b8;margin:0 0 16px;font-size:14px;line-height:1.6;">שלום {driver_name},
      <strong style="color:#F5F5F5;">{passenger_name}</strong> שלח/ה בקשת הצטרפות לנסיעה שלך:</p>
    <table role="presentation" width="100%" style="background:#141414;border:1px solid #252525;border-radius:10px;border-collapse:collapse;">
      <tr>
        <td style="padding:14px 16px;border-bottom:1px solid #252525;">
          <span style="color:#94a3b8;font-size:13px;">{_ICON_PIN} עיר יציאה</span>
          <strong style="color:#F5F5F5;font-size:13px;float:left;">{ride_city}</strong>
        </td>
      </tr>
      <tr>
        <td style="padding:14px 16px;">
          <span style="color:#94a3b8;font-size:13px;">{_ICON_CLOCK} שעת יציאה</span>
          <strong style="color:#F5F5F5;font-size:13px;float:left;">{departure_time}</strong>
        </td>
      </tr>
    </table>
    <p style="color:#666666;font-size:12.5px;margin:18px 0 0;">היכנס/י ל-FastiRide כדי לאשר את הבקשה.</p>
    """
    _send(
        to=driver_email,
        subject="בקשת הצטרפות חדשה לנסיעה שלך – FastiRide",
        html=_wrap_email("בקשת הצטרפות חדשה", body),
    )


def send_cancel_notification(
    driver_email: str,
    driver_name: str,
    passenger_name: str,
    ride_city: str,
) -> None:
    body = f"""
    <p style="color:#94a3b8;margin:0;font-size:14px;line-height:1.6;">שלום {driver_name},
      <strong style="color:#F5F5F5;">{passenger_name}</strong> ביטל/ה את בקשת ההצטרפות
      לנסיעה מ-<strong style="color:#F5F5F5;">{ride_city}</strong>.</p>
    """
    _send(
        to=driver_email,
        subject="ביטול בקשת הצטרפות – FastiRide",
        html=_wrap_email("ביטול בקשת הצטרפות", body),
    )
