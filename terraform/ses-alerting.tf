# ── SES identity for Alertmanager notifications ─────────────────────────────
# SES account is still in sandbox mode (unverified, 200 emails/day cap) — in
# sandbox, BOTH sender and recipient must be verified identities. Using the
# same address for both sides means alerts work immediately with zero AWS
# support ticket / production-access request needed.
resource "aws_ses_email_identity" "alerts_recipient" {
  email = "lidormazor42@gmail.com"
}

# ── Dedicated IAM user for SES SMTP (Alertmanager only speaks SMTP, not the
# AWS API directly — this is intentionally separate from backend_irsa, which
# already has ses:SendRawEmail via IRSA for the app's own notifications) ────
resource "aws_iam_user" "alertmanager_ses_smtp" {
  name = "fastiride-${var.environment}-alertmanager-ses-smtp"
}

resource "aws_iam_user_policy" "alertmanager_ses_smtp" {
  name = "ses-send"
  user = aws_iam_user.alertmanager_ses_smtp.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ses:SendRawEmail"]
      Resource = "*"
    }]
  })
}

resource "aws_iam_access_key" "alertmanager_ses_smtp" {
  user = aws_iam_user.alertmanager_ses_smtp.name
}

output "alertmanager_ses_smtp_username" {
  value = aws_iam_access_key.alertmanager_ses_smtp.id
}

# SES SMTP passwords are NOT the raw IAM secret key — they're derived from it
# via a fixed HMAC-SHA256 algorithm AWS documents. Terraform has no built-in
# hmac() function, so this secret key is exported (sensitive) and converted
# separately with scripts/derive-ses-smtp-password.py — same "run it yourself,
# see what it does" pattern as the rest of this project's infra scripts.
output "alertmanager_ses_smtp_secret_key" {
  value     = aws_iam_access_key.alertmanager_ses_smtp.secret
  sensitive = true
}
