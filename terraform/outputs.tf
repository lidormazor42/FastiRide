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
  description = "Paste this into k8s/overlays/dev/serviceaccount-patch.yaml"
  value       = module.eks.backend_irsa_role_arn
}
