output "bucket_name" {
  description = "Ticket-uploads bucket name — set as S3_UPLOADS_BUCKET on the backend"
  value       = aws_s3_bucket.tickets.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.tickets.arn
}
