#!/usr/bin/env bash
# Tears down everything safely, in the right order, so `terraform destroy`
# doesn't get stuck on resources it doesn't manage (ALB, LBC security groups).
# Run this at the END of every work session.
set -euo pipefail

cd "$(dirname "$0")/../terraform"

echo "==> Deleting ArgoCD Application (cascade-deletes Ingress/ALB properly — otherwise selfHeal fights the helm uninstall below)"
kubectl delete application fastiride-dev -n argocd --wait=true --timeout=120s 2>/dev/null || echo "    (already removed or ArgoCD not installed)"

echo "==> Removing FastiRide Helm release (this deletes the ALB)"
helm uninstall fastiride -n fastiride-dev 2>/dev/null || echo "    (already removed)"

echo "==> Waiting 30s for the ALB and its security groups to fully delete"
sleep 30

echo "==> Running terraform destroy (VPC + EKS only — ECR, GitHub OIDC role, and DNS zone stay alive, they cost ~\$0.50/month total)"
terraform destroy -var-file="dev.tfvars" -target=module.vpc -target=module.eks

echo "==> Verifying no compute is left running (ECR, GitHub OIDC role, and DNS zone are expected to remain)"
terraform state list

echo "==> Done. Check AWS directly if you want extra confidence:"
echo "    aws eks list-clusters   (should be empty)"
echo "    aws ec2 describe-instances --filters Name=instance-state-name,Values=running,pending   (should be empty)"
