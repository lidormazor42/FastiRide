aws_region  = "eu-central-1"
environment = "dev"
vpc_cidr    = "10.0.0.0/16"

kubernetes_version = "1.36"
node_instance_type = "t3.medium"
node_desired_size  = 2
node_min_size      = 1
node_max_size      = 3
