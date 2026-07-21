output "vpc_id" {
  value = module.vpc.vpc_id
}

output "public_subnet_ids" {
  value = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

output "nat_instance_id" {
  description = "NAT Instance (t3.micro) — replaces NAT Gateway, saves ~$32/month"
  value       = module.vpc.nat_instance_id
}

output "backend_ecr_url" {
  value = module.ecr.backend_repository_url
}

output "frontend_ecr_url" {
  value = module.ecr.frontend_repository_url
}

output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "backend_irsa_role_arn" {
  description = "Paste this into helm/fastiride/values-dev.yaml under backend.irsa.roleArn"
  value       = module.eks.backend_irsa_role_arn
}

output "lbc_role_arn" {
  description = "IAM role ARN for AWS Load Balancer Controller"
  value       = module.eks.lbc_role_arn
}

output "karpenter_role_arn" {
  value = module.eks.karpenter_role_arn
}

output "cluster_security_group_id" {
  value = module.eks.cluster_security_group_id
}

output "github_actions_role_arn" {
  description = "IAM role ARN GitHub Actions assumes via OIDC to push to ECR"
  value       = module.github_oidc.role_arn
}

output "ticket_uploads_bucket" {
  description = "S3 bucket for ticket images — set as S3_UPLOADS_BUCKET on the backend"
  value       = module.uploads.bucket_name
}

output "dns_zone_id" {
  description = "Route 53 hosted zone ID for fastiride.app"
  value       = module.dns.zone_id
}

output "dns_name_servers" {
  description = "Paste these into Name.com to delegate fastiride.app to Route 53"
  value       = module.dns.name_servers
}

output "rds_endpoint" {
  description = "RDS Postgres endpoint (host:port) — bootstrap-prod.sh builds DATABASE_URL from this"
  value       = module.rds.endpoint
}

output "rds_ssm_password_parameter" {
  description = "SSM parameter name holding the RDS master password"
  value       = module.rds.ssm_password_parameter_name
}

output "app_session_secret_parameter" {
  description = "SSM parameter name holding the app session-signing secret"
  value       = aws_ssm_parameter.app_session_secret.name
}

output "grafana_admin_password_parameter" {
  description = "SSM parameter name holding the Grafana admin password"
  value       = aws_ssm_parameter.grafana_admin_password.name
}

output "google_client_id_parameter" {
  description = "SSM parameter name holding the Google OAuth client ID"
  value       = aws_ssm_parameter.google_client_id.name
}

output "google_client_secret_parameter" {
  description = "SSM parameter name holding the Google OAuth client secret"
  value       = aws_ssm_parameter.google_client_secret.name
}
