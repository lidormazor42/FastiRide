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
DNS_ZONE_ID=$(terraform output -raw dns_zone_id)
AWS_REGION="us-east-1"
ALB_HOSTED_ZONE_ID="Z35SXDOTRQ7X7K"   # fixed AWS constant for ALBs in us-east-1

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

echo "==> Installing ArgoCD"
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install argocd argo/argo-cd \
  --namespace argocd \
  --create-namespace \
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

echo "==> Registering fastiride-dev Application with ArgoCD"
kubectl apply -f k8s/argocd/app-dev.yaml

echo "==> Waiting for ALB hostname to be assigned"
ALB_HOSTNAME=""
for i in $(seq 1 30); do
  ALB_HOSTNAME=$(kubectl get ingress fastiride -n fastiride-dev -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
  [ -n "$ALB_HOSTNAME" ] && break
  sleep 5
done

if [ -z "$ALB_HOSTNAME" ]; then
  echo "    ALB hostname not ready yet — check 'kubectl get ingress -n fastiride-dev' manually and update DNS."
  exit 1
fi

echo "==> Pointing fastiride.app at $ALB_HOSTNAME"
cat > /tmp/dns-upsert.json <<EOF
{
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "fastiride.app",
      "Type": "A",
      "AliasTarget": {
        "HostedZoneId": "$ALB_HOSTED_ZONE_ID",
        "DNSName": "$ALB_HOSTNAME",
        "EvaluateTargetHealth": true
      }
    }
  }]
}
EOF
aws route53 change-resource-record-sets \
  --hosted-zone-id "$DNS_ZONE_ID" \
  --change-batch file:///tmp/dns-upsert.json

echo "==> Done. fastiride.app now points at $ALB_HOSTNAME"
