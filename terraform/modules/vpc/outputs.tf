output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of public subnets (load balancers)"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of private subnets (EKS nodes)"
  value       = aws_subnet.private[*].id
}

output "nat_instance_id" {
  description = "EC2 instance ID of the NAT instance"
  value       = aws_instance.nat.id
}
