# ── RDS for PostgreSQL — replaces the K8s StatefulSet ──────────────────────
# CLAUDE.md defines RDS as the official architecture (managed, private-subnet
# Postgres with automated backups); the StatefulSet was a deliberate dev-stage
# cost tradeoff, not the end state. See project docs for the FinOps note.

resource "aws_db_subnet_group" "main" {
  name       = "fastiride-${var.environment}-db"
  subnet_ids = var.private_subnet_ids
}

# Only Postgres traffic from inside the VPC — RDS itself is not publicly
# accessible (no internet gateway route from private subnets anyway, this is
# defense in depth). Not scoped to the EKS node security group specifically
# because EKS auto-creates that SG (no clean Terraform reference to it) —
# the VPC CIDR is already private-subnet-only in this network layout.
resource "aws_security_group" "rds" {
  name_prefix = "fastiride-${var.environment}-rds-"
  vpc_id      = var.vpc_id

  ingress {
    description = "Postgres from within the VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "random_password" "master" {
  length  = 24
  special = false # avoid characters that need escaping in connection-string URLs
}

# SecureString in SSM, not a value baked into any .tf file or committed anywhere —
# bootstrap-prod.sh reads this to build the K8s Secret at deploy time.
resource "aws_ssm_parameter" "db_password" {
  name  = "/fastiride/${var.environment}/rds-postgres-password"
  type  = "SecureString"
  value = random_password.master.result
}

resource "aws_db_instance" "main" {
  identifier     = "fastiride-${var.environment}"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.instance_class

  allocated_storage = 20
  storage_type      = "gp3"

  db_name  = "fastiride"
  username = "fastiride"
  password = random_password.master.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  # Single-AZ + skip_final_snapshot: this is a learning project torn down
  # nightly — a snapshot from a fresh, empty DB has no value, and Multi-AZ
  # would double the (already-torn-down-daily) compute cost for no benefit.
  multi_az            = false
  skip_final_snapshot = true
  deletion_protection = false

  backup_retention_period = 1 # the CronJob (separate) is the real backup path
}
