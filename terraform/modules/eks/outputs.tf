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

output "backend_irsa_role_name" {
  description = "Name of the backend IRSA role — other modules attach policies to it"
  value       = aws_iam_role.backend_irsa.name
}

output "lbc_role_arn" {
  description = "ARN of the IAM role for AWS Load Balancer Controller"
  value       = aws_iam_role.lbc.arn
}

output "karpenter_role_arn" {
  description = "ARN of the IAM role for the Karpenter controller (IRSA)"
  value       = aws_iam_role.karpenter.arn
}

output "cluster_security_group_id" {
  description = "EKS-managed cluster security group — used explicitly by Karpenter's EC2NodeClass instead of VPC discovery tags"
  value       = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
}
