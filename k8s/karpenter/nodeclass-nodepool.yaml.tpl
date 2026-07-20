# Templated, NOT a static committed manifest — subnetIDs/securityGroupID are
# dynamic (change on every VPC recreation), unlike the Karpenter controller's
# role ARN (deterministic, hardcoded in k8s/argocd/app-karpenter.yaml).
# Substituted and applied by scripts/karpenter-demo.sh, which reads the real
# current values from `terraform output`.
apiVersion: karpenter.k8s.aws/v1beta1
kind: EC2NodeClass
metadata:
  name: default
spec:
  role: fastiride-dev-eks-node-role
  amiFamily: AL2023
  amiSelectorTerms:
    - alias: al2023@latest
  subnetSelectorTerms:
    - id: __PRIVATE_SUBNET_1__
    - id: __PRIVATE_SUBNET_2__
  securityGroupSelectorTerms:
    - id: __CLUSTER_SECURITY_GROUP__
  tags:
    fastiride/purpose: karpenter-demo
---
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      nodeClassRef:
        name: default
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"] # no spot — cost decision, see PROJECT_BOOK
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["t3.medium"] # match the static node group's instance type
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 1m
  limits:
    cpu: "4" # hard cost ceiling — at most 2 extra t3.medium-equivalent nodes
    memory: 8Gi
