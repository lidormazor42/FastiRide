variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "github_org" {
  description = "GitHub username or organization"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "ecr_repository_arns" {
  description = "ARNs of the ECR repositories GitHub Actions is allowed to push to"
  type        = list(string)
}
