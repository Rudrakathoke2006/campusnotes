#!/bin/bash
# Deletes what the scripts created. Aurora, NAT/VPC, S3 buckets, Lambda trigger, CloudTrail: do in the console (see guide part 14).
source ~/vars.sh
aws autoscaling delete-auto-scaling-group --auto-scaling-group-name cn-asg --force-delete
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN
sleep 60
aws elbv2 delete-target-group --target-group-arn $TG_ARN
aws ec2 delete-launch-template --launch-template-name cn-lt
for m in $(aws efs describe-mount-targets --file-system-id $EFS --query 'MountTargets[].MountTargetId' --output text); do aws efs delete-mount-target --mount-target-id $m; done
sleep 90
aws efs delete-file-system --file-system-id $EFS
aws lambda delete-function --function-name cn-upload-notifier
aws sns delete-topic --topic-arn $TOPIC
aws cognito-idp delete-user-pool --user-pool-id $POOL
aws cloudwatch delete-alarms --alarm-names cn-high-cpu cn-alb-5xx
aws logs delete-log-group --log-group-name campusnotes-app
aws iam remove-role-from-instance-profile --instance-profile-name cn-ec2-profile --role-name cn-ec2-role
aws iam delete-instance-profile --instance-profile-name cn-ec2-profile
aws iam delete-role-policy --role-name cn-ec2-role --policy-name cn-app-access
aws iam detach-role-policy --role-name cn-ec2-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam detach-role-policy --role-name cn-ec2-role --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy
aws iam delete-role --role-name cn-ec2-role
echo "Now in the console: delete Aurora (replica first, no final snapshot), NAT Gateway, release Elastic IP, VPC, empty and delete S3 buckets, CloudTrail, dashboard, budgets."
