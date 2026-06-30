#!/usr/bin/env bash
# Rebuilds everything that lives ON the EKS cluster but is NOT managed by Terraform.
# Run this AFTER `terraform apply` on a freshly created cluster.
# Safe to re-run — every step is idempotent (helm upgrade --install, kubectl apply).
set -euo pipefail

cd "$(dirname "$0")/../terraform"

echo "==> Reading Terraform outputs"
CLUSTER_NAME=$(terraform output -raw eks_cluster_name)
VPC_ID=$(terraform output -raw vpc_id)
LBC_ROLE_ARN=$(terraform output -raw lbc_role_arn)
AWS_REGION="us-east-1"

echo "==> Connecting kubectl to $CLUSTER_NAME"
aws eks update-kubeconfig --region "$AWS_REGION" --name "$CLUSTER_NAME"

echo "==> Installing AWS Load Balancer Controller"
helm repo add eks https://aws.github.io/eks-charts >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  --namespace kube-system \
  --set clusterName="$CLUSTER_NAME" \
  --set serviceAccount.create=true \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"="$LBC_ROLE_ARN" \
  --set region="$AWS_REGION" \
  --set vpcId="$VPC_ID" \
  --wait

echo "==> Creating fastiride-dev namespace"
kubectl create namespace fastiride-dev --dry-run=client -o yaml | kubectl apply -f -

echo "==> Loading secrets from .env"
cd ..
GOOGLE_CLIENT_ID=$(grep '^GOOGLE_CLIENT_ID=' .env | cut -d= -f2-)
GOOGLE_CLIENT_SECRET=$(grep '^GOOGLE_CLIENT_SECRET=' .env | cut -d= -f2-)

echo "==> Creating fastiride-secrets"
kubectl create secret generic fastiride-secrets \
  --namespace fastiride-dev \
  --from-literal=database-url="postgresql://fastiride:fastiride-dev-2026@postgres.fastiride-dev.svc.cluster.local:5432/fastiride" \
  --from-literal=postgres-password="fastiride-dev-2026" \
  --from-literal=session-secret="dev-session-secret-change-in-prod" \
  --from-literal=google-client-id="$GOOGLE_CLIENT_ID" \
  --from-literal=google-client-secret="$GOOGLE_CLIENT_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> Deploying FastiRide via Helm"
helm upgrade --install fastiride helm/fastiride \
  -f helm/fastiride/values.yaml \
  -f helm/fastiride/values-dev.yaml \
  --namespace fastiride-dev \
  --wait

echo "==> Done. Ingress address (DNS already points fastiride.app here):"
kubectl get ingress -n fastiride-dev
