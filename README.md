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

# Preview infrastructure
terraform plan -var-file="dev.tfvars"

# Apply (creates VPC, ECR, EKS)
terraform apply -var-file="dev.tfvars"

# Connect kubectl to the cluster
aws eks update-kubeconfig --region eu-central-1 --name fastiride-dev

# Verify nodes are ready
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
