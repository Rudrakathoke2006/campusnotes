#!/bin/bash
# Needs DB_SECRET saved (from Aurora, guide step 4.3)
set -e
source ~/vars.sh
[ -z "$DB_SECRET" ] && { echo "Set DB_SECRET first (export DB_SECRET=...; save DB_SECRET)"; exit 1; }
cat > /tmp/trust.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
cat > /tmp/app-policy.json <<EOF
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject"],"Resource":"arn:aws:s3:::$BUCKET/*"},
 {"Effect":"Allow","Action":"s3:ListBucket","Resource":"arn:aws:s3:::$BUCKET"},
 {"Effect":"Allow","Action":"secretsmanager:GetSecretValue","Resource":"$DB_SECRET"},
 {"Effect":"Allow","Action":"cognito-idp:AdminConfirmSignUp","Resource":"arn:aws:cognito-idp:ap-south-1:$ACCOUNT:userpool/$POOL"}
]}
EOF
aws iam create-role --role-name cn-ec2-role --assume-role-policy-document file:///tmp/trust.json
aws iam put-role-policy --role-name cn-ec2-role --policy-name cn-app-access --policy-document file:///tmp/app-policy.json
aws iam attach-role-policy --role-name cn-ec2-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam attach-role-policy --role-name cn-ec2-role --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy
aws iam create-instance-profile --instance-profile-name cn-ec2-profile
aws iam add-role-to-instance-profile --instance-profile-name cn-ec2-profile --role-name cn-ec2-role
echo "IAM role ready. Next: 05_efs.sh"
