#!/bin/bash
# Usage: bash 02_services.sh you@example.com   (creates S3, Cognito, SNS)
set -e
source ~/vars.sh
EMAIL=$1
[ -z "$EMAIL" ] && { echo "Usage: bash 02_services.sh you@example.com"; exit 1; }
cd "$(dirname "$0")"

export BUCKET=campusnotes-$(date +%s); save BUCKET
aws s3api create-bucket --bucket $BUCKET --region ap-south-1 --create-bucket-configuration LocationConstraint=ap-south-1
aws s3api put-public-access-block --bucket $BUCKET --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket $BUCKET --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'
aws s3api put-bucket-versioning --bucket $BUCKET --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket $BUCKET --lifecycle-configuration file://lifecycle.json

export POOL=$(aws cognito-idp create-user-pool --pool-name campusnotes-users --username-attributes email --auto-verified-attributes email --query UserPool.Id --output text); save POOL
export CLIENT=$(aws cognito-idp create-user-pool-client --user-pool-id $POOL --client-name cn-web --no-generate-secret --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH --query UserPoolClient.ClientId --output text); save CLIENT

export TOPIC=$(aws sns create-topic --name campusnotes-alerts --query TopicArn --output text); save TOPIC
aws sns subscribe --topic-arn $TOPIC --protocol email --notification-endpoint $EMAIL

echo "Confirm the SNS email. Then create the Lambda (lambda/lambda_function.py) in the console with the S3 trigger (prefix notes/)."
echo "Next: build + upload the app zip with 03_build_and_upload.sh"
