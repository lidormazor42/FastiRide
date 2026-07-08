#!/usr/bin/env bash
# Tears down everything safely, in the right order, so `terraform destroy`
# doesn't get stuck on resources it doesn't manage (ALB, LBC security groups).
# Run this at the END of every work session.
set -euo pipefail

cd "$(dirname "$0")/../terraform"

echo "==> Deleting ArgoCD Applications (cascade-deletes Ingress/ALB properly — otherwise selfHeal fights the helm uninstall below)"
echo "    fastiride-prod, fastiride-staging, and monitoring-grafana all own an Ingress on the SAME shared ALB (group.name: fastiride-shared) — all must go before the ALB fully releases."
kubectl delete application fastiride-prod fastiride-staging monitoring-grafana monitoring-prometheus monitoring-loki -n argocd --wait=true --timeout=120s 2>/dev/null || echo "    (already removed or ArgoCD not installed)"

echo "==> Removing FastiRide Helm releases (prod + staging — this deletes the ALB)"
helm uninstall fastiride -n fastiride-prod 2>/dev/null || echo "    (already removed)"
helm uninstall fastiride-staging -n fastiride-staging 2>/dev/null || echo "    (already removed)"

echo "==> Waiting 30s for the ALB and its security groups to fully delete"
sleep 30

echo "==> Running terraform destroy (VPC + EKS + RDS — ECR, GitHub OIDC role, and DNS zone stay alive, they cost ~\$0.50/month total)"
echo "    RDS deletion (skip_final_snapshot) takes a few minutes on its own — this step will wait for it."
terraform destroy -var-file="dev.tfvars" -target=module.vpc -target=module.eks -target=module.rds

echo "==> Verifying no compute is left running (ECR, GitHub OIDC role, and DNS zone are expected to remain)"
terraform state list

echo "==> Done. Check AWS directly if you want extra confidence:"
echo "    aws eks list-clusters   (should be empty)"
echo "    aws rds describe-db-instances   (should be empty — RDS billing is per-hour just like EC2, don't leave it running)"
echo "    aws ec2 describe-instances --filters Name=instance-state-name,Values=running,pending   (should be empty)"
echo "    aws ec2 describe-volumes --filters Name=status,Values=available   (Prometheus/Loki/Grafana PVCs are EBS-CSI dynamic, still an orphan risk — check every time)"
