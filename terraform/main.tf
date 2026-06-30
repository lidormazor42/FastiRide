terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  backend "s3" {
    bucket  = "fastiride-tfstate-439594592108"
    key     = "fastiride/dev/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "fastiride"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

# ── VPC ──────────────────────────────────────────────────────────────────────
module "vpc" {
  source = "./modules/vpc"

  environment          = var.environment
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  availability_zones   = var.availability_zones
}

# ── ECR ──────────────────────────────────────────────────────────────────────
module "ecr" {
  source = "./modules/ecr"

  environment = var.environment
}

# ── EKS ──────────────────────────────────────────────────────────────────────
module "eks" {
  source = "./modules/eks"

  environment         = var.environment
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids   # nodes in private subnets
  kubernetes_version  = var.kubernetes_version
  node_instance_type  = var.node_instance_type
  node_desired_size   = var.node_desired_size
  node_min_size       = var.node_min_size
  node_max_size       = var.node_max_size
}

# ── GitHub OIDC — lets GitHub Actions push to ECR without static AWS keys ─────
module "github_oidc" {
  source = "./modules/github-oidc"

  environment = var.environment
  github_org  = "lidormazor42"
  github_repo = "FastiRide"
  ecr_repository_arns = [
    module.ecr.backend_repository_arn,
    module.ecr.frontend_repository_arn,
  ]
}

# ── DNS — Route 53 hosted zone for fastiride.app ──────────────────────────────
# Persistent: not destroyed in the daily teardown, costs ~$0.50/month flat.
# The A record itself is updated by scripts/bootstrap-dev.sh on every deploy.
module "dns" {
  source = "./modules/dns"

  domain_name = "fastiride.app"
}
