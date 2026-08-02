aws_region  = "us-east-1"
environment = "dev"

vpc_cidr             = "10.0.0.0/16"
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.11.0/24", "10.0.12.0/24"]
availability_zones   = ["us-east-1a", "us-east-1b"]

kubernetes_version = "1.36"
node_instance_type = "t3.medium"
node_desired_size  = 2
node_min_size      = 1
node_max_size      = 3

# Temporarily opened wide for the 5.8 presentation (moving networks —
# examiner's venue — makes the usual IP-lock a live risk mid-demo; IAM auth
# is still required to actually talk to the API either way). Lock this back
# down to a single IP after the cluster's next teardown/raise cycle.
eks_public_access_cidrs = ["0.0.0.0/0"]
