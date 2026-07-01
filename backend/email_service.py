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


def send_join_notification(
    driver_email: str,
    driver_name: str,
    passenger_name: str,
    ride_city: str,
    departure_time: str,
) -> None:
    _send(
        to=driver_email,
        subject="בקשת הצטרפות חדשה לנסיעה שלך – FastiRide",
        html=f"""
        <div dir="rtl" style="font-family:Arial,sans-serif;padding:24px;max-width:480px;
             background:#0A0A0A;color:#F5F5F5;border-radius:12px;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;">
            <span style="font-size:22px;font-weight:900;color:#F5F5F5;">FastiRide</span>
            <span style="font-size:18px;color:#FF3300;">⚡</span>
          </div>
          <h2 style="color:#FF3300;margin-bottom:8px;">שלום {driver_name},</h2>
          <p style="color:#94a3b8;"><strong style="color:#F5F5F5;">{passenger_name}</strong>
             שלח/ה בקשת הצטרפות לנסיעה שלך:</p>
          <div style="background:#141414;border:1px solid #252525;border-radius:8px;
               padding:16px;margin:16px 0;">
            <p style="margin:4px 0;color:#94a3b8;">🚀 עיר יציאה:
               <strong style="color:#F5F5F5;">{ride_city}</strong></p>
            <p style="margin:4px 0;color:#94a3b8;">🕐 שעת יציאה:
               <strong style="color:#F5F5F5;">{departure_time}</strong></p>
          </div>
          <p style="color:#666666;font-size:13px;">היכנס/י ל-FastiRide כדי לאשר את הבקשה.</p>
        </div>
        """,
    )


def send_cancel_notification(
    driver_email: str,
    driver_name: str,
    passenger_name: str,
    ride_city: str,
) -> None:
    _send(
        to=driver_email,
        subject="ביטול בקשת הצטרפות – FastiRide",
        html=f"""
        <div dir="rtl" style="font-family:Arial,sans-serif;padding:24px;max-width:480px;
             background:#0A0A0A;color:#F5F5F5;border-radius:12px;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;">
            <span style="font-size:22px;font-weight:900;color:#F5F5F5;">FastiRide</span>
            <span style="font-size:18px;color:#FF3300;">⚡</span>
          </div>
          <h2 style="color:#FF3300;margin-bottom:8px;">שלום {driver_name},</h2>
          <p style="color:#94a3b8;"><strong style="color:#F5F5F5;">{passenger_name}</strong>
             ביטל/ה את בקשת ההצטרפות לנסיעה מ-<strong style="color:#F5F5F5;">{ride_city}</strong>.</p>
        </div>
        """,
    )
