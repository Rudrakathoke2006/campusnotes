#!/bin/bash
# Run AFTER creating the VPC with the console wizard (name prefix: cn)
set -e
source ~/vars.sh
export VPC=$(aws ec2 describe-vpcs --filters Name=tag:Name,Values=cn-vpc --query 'Vpcs[0].VpcId' --output text); save VPC
sn() { aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC Name=tag:Name,Values=$1 --query 'Subnets[0].SubnetId' --output text; }
export PUB_A=$(sn 'cn-subnet-public1-*'); export PUB_B=$(sn 'cn-subnet-public2-*')
export APP_A=$(sn 'cn-subnet-private1-*'); export APP_B=$(sn 'cn-subnet-private2-*')
for v in PUB_A PUB_B APP_A APP_B; do save $v; done

export DB_A=$(aws ec2 create-subnet --vpc-id $VPC --cidr-block 10.0.64.0/24 --availability-zone ap-south-1a --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=cn-db-a}]' --query Subnet.SubnetId --output text)
export DB_B=$(aws ec2 create-subnet --vpc-id $VPC --cidr-block 10.0.65.0/24 --availability-zone ap-south-1b --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=cn-db-b}]' --query Subnet.SubnetId --output text)
save DB_A; save DB_B

mk() { aws ec2 create-security-group --group-name $1 --description $1 --vpc-id $VPC --query GroupId --output text; }
export ALB_SG=$(mk cn-alb-sg); export APP_SG=$(mk cn-app-sg); export DB_SG=$(mk cn-db-sg); export EFS_SG=$(mk cn-efs-sg)
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $APP_SG --protocol tcp --port 8000 --source-group $ALB_SG
aws ec2 authorize-security-group-ingress --group-id $DB_SG  --protocol tcp --port 3306 --source-group $APP_SG
aws ec2 authorize-security-group-ingress --group-id $EFS_SG --protocol tcp --port 2049 --source-group $APP_SG
for v in ALB_SG APP_SG DB_SG EFS_SG; do save $v; done

aws rds create-db-subnet-group --db-subnet-group-name cn-db-subnets --db-subnet-group-description CampusNotes --subnet-ids $DB_A $DB_B
echo "Done. Next: create Aurora in the console (guide part 4), then save DB_HOST and DB_SECRET, then run 02_services.sh"
