variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID (used for security group)"
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs for EKS nodes"
  type        = list(string)
}

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "EC2 instance type for nodes"
  type        = string
  default     = "t3.medium"
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_min_size" {
  type    = number
  default = 1
}

variable "public_access_cidrs" {
  description = "CIDRs allowed to reach the EKS public API endpoint. Defaults to open (0.0.0.0/0) so a fresh apply never locks anyone out by surprise — narrow it explicitly via dev.tfvars."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "node_max_size" {
  type    = number
  default = 3
}
