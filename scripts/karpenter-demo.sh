#!/usr/bin/env bash
# Applies the EC2NodeClass/NodePool with real, current subnet/SG IDs
# substituted from `terraform output` (they're dynamic — different every time
# the VPC is recreated, unlike the Karpenter controller's role ARN which is
# deterministic and lives as a static committed manifest instead).
#
# Run this only when actually demoing Karpenter — call with `down` afterward
# to remove the NodePool so no further nodes get provisioned.
set -euo pipefail
cd "$(dirname "$0")/../terraform"

if [ "${1:-up}" = "down" ]; then
  echo "==> Removing NodePool (stops further provisioning) and EC2NodeClass"
  kubectl delete nodepool default --ignore-not-found
  kubectl delete ec2nodeclass default --ignore-not-found
  echo "==> Done. Karpenter controller itself is left running (idle, ~100m CPU/128Mi) — it's ArgoCD-managed like metrics-server."
  exit 0
fi

SUBNET_1=$(terraform output -json private_subnet_ids | python3 -c "import json,sys; print(json.load(sys.stdin)[0])")
SUBNET_2=$(terraform output -json private_subnet_ids | python3 -c "import json,sys; print(json.load(sys.stdin)[1])")
SG_ID=$(terraform output -raw cluster_security_group_id)

echo "==> Applying EC2NodeClass/NodePool with:"
echo "    subnets: $SUBNET_1, $SUBNET_2"
echo "    security group: $SG_ID"

sed \
  -e "s/__PRIVATE_SUBNET_1__/${SUBNET_1}/" \
  -e "s/__PRIVATE_SUBNET_2__/${SUBNET_2}/" \
  -e "s/__CLUSTER_SECURITY_GROUP__/${SG_ID}/" \
  ../k8s/karpenter/nodeclass-nodepool.yaml.tpl | kubectl apply -f -

echo "==> Done. Watch provisioning with: kubectl get nodeclaims -w"
