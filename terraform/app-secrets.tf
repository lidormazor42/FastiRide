# ── Application-level secrets ──────────────────────────────────────────────
# Same pattern as the RDS master password (modules/rds): generated once by
# Terraform, stored in SSM Parameter Store as SecureString, read at bootstrap
# time by scripts/bootstrap-prod.sh into Kubernetes Secrets. These replaced
# hardcoded values that used to live in the bootstrap script itself (and
# therefore in Git) — the session secret signs every user's auth cookie, so
# anyone reading the repo could have forged sessions.
#
# These live OUTSIDE the vpc/eks/rds modules on purpose: they survive the
# nightly teardown (teardown-prod.sh only destroys vpc+eks+rds), so secrets
# stay stable across cluster rebuilds — user sessions from before a teardown
# still verify after the next bootstrap.

resource "random_password" "app_session_secret" {
  length  = 64
  special = false # HMAC key material — alphanumeric avoids shell/YAML quoting pitfalls
}

resource "aws_ssm_parameter" "app_session_secret" {
  name  = "/fastiride/${var.environment}/app-session-secret"
  type  = "SecureString"
  value = random_password.app_session_secret.result
}

resource "random_password" "grafana_admin_password" {
  length  = 24
  special = false
}

resource "aws_ssm_parameter" "grafana_admin_password" {
  name  = "/fastiride/${var.environment}/grafana-admin-password"
  type  = "SecureString"
  value = random_password.grafana_admin_password.result
}

# Google OAuth credentials — not generated (they come from Google Cloud
# Console), just relayed into SSM so bootstrap-prod.sh has one consistent
# source for every secret instead of reading these two specifically from
# .env. See variables.tf for where the actual values come from.
resource "aws_ssm_parameter" "google_client_id" {
  name  = "/fastiride/${var.environment}/google-client-id"
  type  = "SecureString"
  value = var.google_client_id
}

resource "aws_ssm_parameter" "google_client_secret" {
  name  = "/fastiride/${var.environment}/google-client-secret"
  type  = "SecureString"
  value = var.google_client_secret
}
