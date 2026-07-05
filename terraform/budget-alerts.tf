# ── Cost guardrails ────────────────────────────────────────────────────────
# Soft early-warning alert — fires at 50% of actual spend against a $20/month
# budget. Originally created by hand in the AWS console (2026-06-01); brought
# under Terraform via `terraform import` on 2026-07-05 so it's no longer an
# unmanaged, undocumented resource.
resource "aws_budgets_budget" "monthly_limit_20" {
  name              = "fastiride-monthly-limit"
  budget_type       = "COST"
  limit_amount      = "20.0"
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2026-06-01_00:00"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["lidormazor42@gmail.com"]
  }
}

# Hard ceiling alert — fires once actual spend for the month hits $100.
# Separate from the $20 "soft" budget above so this one has a clear, single
# job: catch a runaway bill before it gets serious, independent of the
# day-to-day $20 tracking.
resource "aws_budgets_budget" "hard_limit_100" {
  name         = "fastiride-hard-limit-100"
  budget_type  = "COST"
  limit_amount = "100"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["lidormazor42@gmail.com"]
  }
}
