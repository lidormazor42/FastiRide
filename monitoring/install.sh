#!/bin/bash
# One-shot monitoring stack install — run once after terraform apply + kubeconfig setup
# Usage: bash monitoring/install.sh

set -e

echo "→ Adding Helm repos..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana              https://grafana.github.io/helm-charts
helm repo update

echo "→ Installing Prometheus..."
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f monitoring/prometheus/values.yaml \
  --wait

echo "→ Installing Loki + Promtail..."
helm upgrade --install loki grafana/loki-stack \
  --namespace monitoring --create-namespace \
  -f monitoring/loki/values.yaml \
  --wait

echo "→ Installing Grafana..."
helm upgrade --install grafana grafana/grafana \
  --namespace monitoring --create-namespace \
  -f monitoring/grafana/values.yaml \
  --wait

echo ""
echo "✓ Done! Access Grafana:"
echo "  kubectl port-forward -n monitoring svc/grafana 3000:80"
echo "  Open: http://localhost:3000  (admin / see values.yaml)"
