# FastiRide

A ride-sharing platform for festival attendees — built as an end-to-end DevOps capstone project. The app itself (who's driving where) is secondary to the point of the exercise: a real application, fully containerized, deployed to a managed Kubernetes cluster on AWS, with GitOps continuous delivery and full observability, defined entirely as code.

## Stack

| Layer | Technology | Why |
|---|---|---|
| Backend | FastAPI (Python) | async-native, automatic OpenAPI docs, easy to instrument |
| Frontend | Nginx + vanilla HTML/JS | no build step, keeps the container tiny |
| Database | Amazon RDS (PostgreSQL 16) | managed backups/patching — see FinOps log for why this replaced a StatefulSet |
| Container Runtime | Docker | standard, and what Compose/K8s both expect |
| Orchestration | Kubernetes (Amazon EKS) | the actual subject of the course |
| Packaging | Helm | one chart, two value files (`values.yaml` + `values-prod.yaml`) — no duplicated manifests |
| IaC | Terraform (S3 remote state) | every AWS resource is code, nothing clicked into existence |
| CI | GitHub Actions | lint → unit tests → build → push → GitOps commit |
| CD | ArgoCD | pulls from Git, not pushed to by CI — Git is the only source of truth |
| Metrics | Prometheus (kube-prometheus-stack) | scrapes the cluster *and* a custom `/metrics` endpoint on the backend |
| Dashboards | Grafana | one custom dashboard (RED method) built for this app's actual metrics |
| Logs | Grafana Loki + Promtail | log aggregation without running an Elasticsearch cluster |
| Alerting | Alertmanager → SES (email) | real notifications, not just dashboards nobody looks at |
| Secrets | AWS SSM Parameter Store (SecureString) | nothing sensitive committed to Git |

## Architecture

```mermaid
flowchart TB
    subgraph Internet
        User[Browser]
    end

    User -->|HTTPS| R53[Route 53<br/>fastiride.app]
    R53 --> ALB[AWS ALB<br/>shared across app + Grafana]

    subgraph AWS["AWS VPC (us-east-1, 2 AZs)"]
        subgraph Public["Public subnets"]
            ALB
            NAT[NAT Instance<br/>t3.micro]
        end

        subgraph Private["Private subnets"]
            subgraph EKS["EKS Cluster"]
                FE[frontend<br/>x2 replicas]
                BE[backend<br/>x1 replica]
                subgraph Monitoring["monitoring namespace"]
                    Prom[Prometheus]
                    Graf[Grafana]
                    Loki[Loki]
                    AM[Alertmanager]
                end
            end
            RDS[(RDS PostgreSQL)]
        end

        ALB --> FE
        ALB -->|/api| BE
        ALB -->|grafana.fastiride.app| Graf
        BE --> RDS
        BE -.->|outbound only| NAT --> IGW[Internet Gateway]
        Prom -->|scrapes /metrics| BE
        Graf --> Prom
        Graf --> Loki
        Prom --> AM
    end

    BE --> S3[(S3<br/>ticket uploads + DB backups)]
    BE --> SES[Amazon SES]
    BE --> Rek[Rekognition<br/>ticket OCR]
    AM -->|email| SES
    CronJob[CronJob: pg_dump] --> RDS
    CronJob --> S3

    subgraph GitHub
        Repo[FastiRide repo]
        Actions[GitHub Actions]
    end

    Dev[git push] --> Repo
    Repo --> Actions
    Actions -->|lint + pytest| Actions
    Actions -->|build + push| ECR[(ECR)]
    Actions -->|bump image tag| Repo
    ArgoCD[ArgoCD] -->|polls & syncs| Repo
    ArgoCD --> EKS
```

**How a deploy actually happens:** push to `main` → GitHub Actions lints, runs the pytest suite, and (only if both pass) builds and pushes Docker images to ECR → CI commits the new image tag back into `helm/fastiride/values.yaml` (a "GitOps trigger", not a direct deploy) → ArgoCD notices the Git change on its next poll and applies it to the cluster. **Nothing ever deploys by CI pushing to the cluster directly** — Git is the only thing ArgoCD trusts.

### Environments

This project deliberately has **one AWS account/region**, not a separate dev+prod AWS footprint — that would double the cost for a personal project with a single maintainer. Instead:

| | Local (dev) | AWS/EKS (prod) |
|---|---|---|
| How it runs | `docker compose up` | `terraform apply` + `./scripts/bootstrap-prod.sh` |
| Database | Postgres container | Amazon RDS |
| Where code lands | not deployed anywhere | `fastiride.app`, via ALB + Route 53 |
| Torn down | `docker compose down` | `./scripts/teardown-prod.sh` — nightly, to control cost |

### GitFlow

`main` is what ArgoCD watches — every merge into it is a real deploy. Day-to-day work happens on `develop` and short-lived `feature/*` branches; a pull request into `develop` runs lint + unit tests before it can merge, and `develop` merges into `main` when a change is ready to actually go live.

### FinOps Decision Log

| Decision | What | Why |
|---|---|---|
| NAT Instance, not NAT Gateway | t3.micro EC2 acting as router | Saves ~$32/month vs. a managed NAT Gateway |
| RDS, not a K8s StatefulSet | Managed Postgres in a private subnet | Automated backups/patching; this *was* a StatefulSet during early development to save cost while iterating fast — migrated once the schema stabilized (see Problems & Solutions) |
| Loki, not ELK | Grafana Loki + Promtail | An Elasticsearch cluster is heavy for this scale; Loki integrates natively with the same Grafana already in use for metrics |
| Alertmanager → SES, not Slack | Reused the SES identity already set up for the app's own notifications | Zero new external accounts/services to configure |
| Self-hosted monitoring, not CloudWatch | Prometheus/Grafana/Loki inside the cluster | CloudWatch Logs bills per GB ingested — self-hosting on already-provisioned nodes is close to free (see below) |
| Hand-written Terraform modules, not the public registry ones | Custom `vpc`/`eks`/`rds`/etc. modules | Full control over exactly what gets created — easier to explain every single resource in an exam setting than a large third-party module with defaults you didn't choose |
| One shared ALB, not two | Grafana's Ingress uses the same `alb.ingress.kubernetes.io/group.name` as the app's | Avoids paying for and managing a second load balancer just to expose a dashboard |
| VPC CNI prefix delegation | `ENABLE_PREFIX_DELEGATION=true` + custom `maxPods` on the node launch template | Raised the pods-per-node ceiling from 17 to 110 for free, instead of adding a third EC2 node |

**Actual added cost of Monitoring:** ~$3.50/month (35GB of EBS storage for Prometheus/Loki/Grafana) — no extra compute (reuses existing node headroom) and no extra load balancer. This project runs almost entirely on the free part of the AWS bill; the two AWS Budget alerts in `terraform/budget-alerts.tf` exist specifically to catch anything that stops being true.

## Project Structure

```
FastiRide/
├── backend/            FastAPI app, Dockerfile, tests/ (pytest)
├── frontend/            Nginx + HTML/JS, Dockerfile
├── terraform/           IaC — vpc, ecr, eks, rds, uploads (S3), dns, github-oidc, budget-alerts, ses-alerting
├── helm/fastiride/       Helm chart — Deployments, Service, Ingress, HPA, Postgres backup CronJob
├── k8s/argocd/           ArgoCD Application manifests (app + monitoring stack)
├── monitoring/           Prometheus/Loki/Grafana values.yaml — deployed via ArgoCD, not manual helm
├── scripts/              bootstrap-prod.sh / teardown-prod.sh / derive-ses-smtp-password.py
├── .github/workflows/    CI: lint → pytest → build → push → GitOps bump
├── PROJECT_BOOK.md       Full write-up in Hebrew (architecture, tools, problems & solutions, exam prep)
└── docs/images/          Screenshots referenced below
```

## Getting Started

### Prerequisites

AWS CLI, Terraform >= 1.6, kubectl, Helm, Docker, `gh` CLI. Everything below assumes AWS credentials with permission to create the resources in `terraform/`.

### Local development (dev)

```bash
docker compose up -d
# Backend:  http://localhost:8000
# Frontend: http://localhost
```

### AWS deployment (prod)

```bash
cd terraform
terraform init
terraform apply -var-file="dev.tfvars"   # yes, "dev.tfvars" — see naming note below
cd ..
./scripts/bootstrap-prod.sh              # installs LBC, ArgoCD, secrets, then registers everything with ArgoCD
```

**Naming note:** AWS resources (`fastiride-dev` cluster, IAM roles, etc.) kept their original `dev` names — renaming them would mean destroying and recreating the whole cluster for a cosmetic change. The Kubernetes-level naming (`fastiride-prod` namespace, `fastiride.app` domain) is what actually reflects that this is the live/production environment.

### Accessing ArgoCD and Grafana

```bash
kubectl port-forward -n argocd svc/argocd-server 8080:443
# https://localhost:8080 — username `admin`, password: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```

Grafana is public at `https://grafana.fastiride.app` (no port-forward needed — see the shared-ALB decision above).

### Tear down (stop paying)

```bash
./scripts/teardown-prod.sh
```

Deletes the ArgoCD-managed apps first (so the ALB gets cleanly released), then destroys VPC/EKS/RDS via Terraform. ECR, the Route 53 zone, and the S3 buckets are deliberately left alive — they cost about $0.50/month combined.

## Screenshots

_Add these to `docs/images/` and reference them here before submitting:_

- [ ] `docs/images/app-board.png` — the ride board in the browser
- [ ] `docs/images/argocd-apps.png` — ArgoCD showing all Applications Synced/Healthy
- [ ] `docs/images/grafana-red-dashboard.png` — the custom FastiRide Backend dashboard
- [ ] `docs/images/grafana-cluster-dashboard.png` — the Kubernetes Cluster Overview dashboard
- [ ] `docs/images/ci-pipeline.png` — a green GitHub Actions run (lint → test → build → push)
- [ ] `docs/images/rds-console.png` — the RDS instance, `available`

## Managing the Cluster with k9s

k9s is a terminal UI for Kubernetes — faster to navigate than raw `kubectl` once the cluster is up.

```bash
k9s                # launch
k9s -n monitoring  # open directly in a namespace
k9s --readonly     # safe browsing mode
```

| Shortcut | Action |
|---|---|
| `:pod` / `:deploy` / `:svc` | switch resource view |
| `:ns` | switch namespace |
| `l` | view logs |
| `d` | describe |
| `s` | shell into container |
| `ctrl-d` | delete |
| `?` | all shortcuts |
