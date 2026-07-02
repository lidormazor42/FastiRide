# ── S3 bucket for festival-ticket image uploads ───────────────────────────────
# Persistent (survives the daily teardown like ECR/DNS) — storage cost is
# effectively zero at this scale. The backend archives every validated
# ticket image here; Rekognition reads happen on raw bytes, not from S3.

resource "aws_s3_bucket" "tickets" {
  bucket        = "fastiride-${var.environment}-ticket-uploads"
  force_destroy = true # dev bucket — allow destroy even when non-empty
}

resource "aws_s3_bucket_public_access_block" "tickets" {
  bucket = aws_s3_bucket.tickets.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Tickets are transient evidence — expire them after 90 days to cap storage.
resource "aws_s3_bucket_lifecycle_configuration" "tickets" {
  bucket = aws_s3_bucket.tickets.id

  rule {
    id     = "expire-old-tickets"
    status = "Enabled"

    filter {
      prefix = "tickets/"
    }

    expiration {
      days = 90
    }
  }
}

# ── Backend pod permissions (attached to the existing IRSA role) ──────────────
# put/get on this bucket only + Rekognition text detection. Nothing else.
resource "aws_iam_role_policy" "backend_uploads" {
  count = var.backend_role_name == "" ? 0 : 1

  name = "ticket-uploads-and-rekognition"
  role = var.backend_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject"]
        Resource = "${aws_s3_bucket.tickets.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = "rekognition:DetectText"
        Resource = "*" # Rekognition has no resource-level ARNs for DetectText
      },
    ]
  })
}
