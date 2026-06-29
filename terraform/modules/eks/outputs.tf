output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_ca_certificate" {
  description = "Base64-encoded cluster CA certificate"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "oidc_provider_arn" {
  description = "ARN of the OIDC provider (used for additional IRSA roles)"
  value       = aws_iam_openid_connect_provider.eks.arn
}

output "backend_irsa_role_arn" {
  description = "ARN of the IAM role for the backend service account (SES)"
  value       = aws_iam_role.backend_irsa.arn
}

output "lbc_role_arn" {
  description = "ARN of the IAM role for AWS Load Balancer Controller"
  value       = aws_iam_role.lbc.arn
}
