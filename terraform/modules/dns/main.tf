# ── Route 53 Hosted Zone — DNS for fastiride.app ──────────────────────────────
# Nameservers must be set at the domain registrar (Name.com) to delegate
# DNS resolution to this zone. The A record itself is updated by
# scripts/bootstrap-dev.sh after each deploy, since the ALB hostname
# changes every time the cluster is rebuilt.
resource "aws_route53_zone" "main" {
  name = var.domain_name
}
