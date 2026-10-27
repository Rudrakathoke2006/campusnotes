#!/bin/bash
# Run first, in AWS CloudShell:  bash 00_setup.sh
cat > ~/vars.sh <<'EOF'
export AWS_REGION=ap-south-1
export AWS_DEFAULT_REGION=ap-south-1
save() { echo "export $1='${!1}'" >> ~/vars.sh; }
EOF
source ~/vars.sh
export ACCOUNT=$(aws sts get-caller-identity --query Account --output text); save ACCOUNT
export AMI_LINUX=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text); save AMI_LINUX
echo "Account: $ACCOUNT  AMI: $AMI_LINUX"
echo "Next: create the VPC in the console (wizard, prefix cn), then run 01_network.sh"
