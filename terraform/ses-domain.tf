# ── SES domain identity for the app's own sender address ──────────────────
# Real bug found 2026-07-08: the backend has been sending from
# "noreply@fastiride.app" (config.sesSenderEmail in Helm values) since it was
# built, but that address was never verified in SES — every join/cancel
# notification email has been failing silently (email_service.py's
# try/except swallows the ClientError and falls back to a console-only mock).
#
# Verifying the whole DOMAIN (not just one address) via DKIM means ANY
# address @fastiride.app can send — no per-address email-click verification
# needed, it's pure DNS, so Terraform can do the entire thing.
resource "aws_sesv2_email_identity" "app_domain" {
  email_identity = "fastiride.app"
}

resource "aws_route53_record" "ses_dkim" {
  count   = 3
  zone_id = module.dns.zone_id
  name    = "${aws_sesv2_email_identity.app_domain.dkim_signing_attributes[0].tokens[count.index]}._domainkey.fastiride.app"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_sesv2_email_identity.app_domain.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}
