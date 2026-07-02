variable "environment" {
  description = "Environment name (dev/prod) — used in the bucket name"
  type        = string
}

variable "backend_role_name" {
  description = "Name of the backend IRSA role to grant S3+Rekognition access. Empty string skips the policy (bucket-only mode, e.g. when EKS is torn down)."
  type        = string
  default     = ""
}
