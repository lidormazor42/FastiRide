output "vpc_id" {
  description = "The ID of the FastiRide VPC"
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = module.vpc.public_subnet_ids
}

output "backend_repository_url" {
  description = "ECR URL for the backend image"
  value       = module.ecr.backend_repository_url
}

output "frontend_repository_url" {
  description = "ECR URL for the frontend image"
  value       = module.ecr.frontend_repository_url
}

output "eks_cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "API endpoint of the EKS cluster"
  value       = module.eks.cluster_endpoint
}
