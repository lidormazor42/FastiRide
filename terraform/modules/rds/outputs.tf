output "endpoint" {
  description = "RDS connection endpoint (host:port)"
  value       = aws_db_instance.main.endpoint
}

output "address" {
  description = "RDS host only, no port"
  value       = aws_db_instance.main.address
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "username" {
  value = aws_db_instance.main.username
}

output "ssm_password_parameter_name" {
  description = "SSM parameter bootstrap-prod.sh reads to build the K8s secret"
  value       = aws_ssm_parameter.db_password.name
}
