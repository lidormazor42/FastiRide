# FastiRide

A production-grade ride-sharing platform for festival attendees, built as a DevOps capstone project.

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) |
| Frontend | Nginx + HTML/CSS |
| Database | PostgreSQL (StatefulSet) |
| Container Runtime | Docker |
| Orchestration | Kubernetes (AWS EKS) |
| IaC | Terraform |
| CI | GitHub Actions |
| CD | ArgoCD (GitOps) |
| Monitoring | Prometheus + Grafana + ELK |

## Architecture

### Environments

| | Dev | Prod |
|---|---|---|
| Region | us-east-1 | us-east-1 |
| Availability Zones | 1 (us-east-1a) | 3 (1a / 1b / 1c) |
| NAT Strategy | NAT Instance (t3.micro) | NAT Instance x2 (t3.small) |
| Database | PostgreSQL StatefulSet | PostgreSQL StatefulSet (Primary + Replica) |
| Load Balancer | NodePort | AWS ALB (Multi-AZ) |

### FinOps Decision Log

**NAT Instance over NAT Gateway:** Both environments use EC2-based NAT Instances
instead of AWS-managed NAT Gateways. This saves ~$32–64/month per environment.
Trade-off: requires manual patching and CloudWatch-based health monitoring.
Migration path to NAT Gateway is a single Terraform variable change if throughput
requirements exceed instance limits.

**PostgreSQL in-cluster:** Using a StatefulSet instead of RDS saves ~$100–150/month
in dev and prod. Acceptable for a capstone project; production business workloads
should evaluate RDS Multi-AZ for automated failover SLA.

## Project Structure

```
FastiRide/
├── backend/          # FastAPI app + Dockerfile
├── frontend/         # Nginx + HTML + Dockerfile
├── terraform/        # IaC — VPC, ECR, EKS modules
├── k8s/              # Kubernetes manifests (base + overlays)
├── helm/             # Helm charts
├── monitoring/       # Prometheus, Grafana, ELK configs
└── .github/workflows # CI/CD pipelines
```

## Getting Started

### Prerequisites

- AWS CLI configured
- Terraform >= 1.0.0
- kubectl
- k9s (optional but recommended)
- Helm

### Infrastructure Setup

```bash
# Initialize Terraform
cd terraform
terraform init
```

#### Deploy Dev Environment

```bash
terraform plan -var-file="dev.tfvars"
terraform apply -var-file="dev.tfvars"
aws eks update-kubeconfig --region us-east-1 --name fastiride-dev
kubectl get nodes
```

#### Deploy Prod Environment

```bash
terraform plan -var-file="prod.tfvars"
terraform apply -var-file="prod.tfvars"
aws eks update-kubeconfig --region us-east-1 --name fastiride-prod
kubectl get nodes
```

### Tear down

```bash
terraform destroy -var-file="dev.tfvars"
```

## Managing the Cluster with k9s

k9s is a terminal UI for Kubernetes that makes cluster management much easier than raw kubectl commands.

### Launch k9s

```bash
k9s
```

### Essential k9s shortcuts

| Shortcut | Action |
|---|---|
| `:pod` | View all pods |
| `:deploy` | View deployments |
| `:svc` | View services |
| `:ns` | Switch namespace |
| `l` | View pod logs |
| `d` | Describe resource |
| `s` | Shell into container |
| `ctrl-d` | Delete resource |
| `?` | Show all shortcuts |
| `:q` | Quit |

### Useful k9s commands

```bash
# Open k9s in a specific namespace
k9s -n kube-system

# Open in read-only mode (safe for production)
k9s --readonly

# View k9s info (log locations, config path)
k9s info
```

## Local Development

```bash
# Run locally with Docker Compose
docker-compose up

# Backend available at: http://localhost:8000
# Frontend available at: http://localhost:80
```
