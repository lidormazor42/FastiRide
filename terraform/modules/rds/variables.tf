variable "environment" {
  description = "Deployment environment (dev or prod)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID the RDS instance lives in"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block — RDS security group allows Postgres from within it only"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for the DB subnet group (same subnets as EKS nodes)"
  type        = list(string)
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}
