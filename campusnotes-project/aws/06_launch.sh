#!/bin/bash
# Launch template + ALB + Auto Scaling + alarms. Run after the zip is in S3.
set -e
source ~/vars.sh
cd "$(dirname "$0")"
sed -e "s|__BUCKET__|$BUCKET|g" -e "s|__DB_HOST__|$DB_HOST|g" -e "s|__DB_SECRET__|$DB_SECRET|g" -e "s|__POOL__|$POOL|g" -e "s|__CLIENT__|$CLIENT|g" -e "s|__SECRET_KEY__|$SECRET_KEY|g" -e "s|__EFS__|$EFS|g" userdata.tpl > /tmp/userdata.sh
if grep -q '__' /tmp/userdata.sh; then echo "A placeholder was left blank. Check your variables."; exit 1; fi

cat > /tmp/lt.json <<EOF
{
 "ImageId":"$AMI_LINUX",
 "InstanceType":"t3.micro",
 "IamInstanceProfile":{"Name":"cn-ec2-profile"},
 "SecurityGroupIds":["$APP_SG"],
 "Monitoring":{"Enabled":true},
 "MetadataOptions":{"HttpTokens":"required"},
 "BlockDeviceMappings":[
  {"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":8,"VolumeType":"gp3","Encrypted":true,"DeleteOnTermination":true}},
  {"DeviceName":"/dev/sdf","Ebs":{"VolumeSize":5,"VolumeType":"gp3","Encrypted":true,"DeleteOnTermination":true}}],
 "UserData":"$(base64 -w0 /tmp/userdata.sh)"
}
EOF
aws ec2 create-launch-template --launch-template-name cn-lt --launch-template-data file:///tmp/lt.json

export TG_ARN=$(aws elbv2 create-target-group --name cn-tg --protocol HTTP --port 8000 --vpc-id $VPC --health-check-path /health --target-type instance --query 'TargetGroups[0].TargetGroupArn' --output text); save TG_ARN
export ALB_ARN=$(aws elbv2 create-load-balancer --name cn-alb --subnets $PUB_A $PUB_B --security-groups $ALB_SG --query 'LoadBalancers[0].LoadBalancerArn' --output text); save ALB_ARN
aws elbv2 create-listener --load-balancer-arn $ALB_ARN --protocol HTTP --port 80 --default-actions Type=forward,TargetGroupArn=$TG_ARN

aws autoscaling create-auto-scaling-group --auto-scaling-group-name cn-asg --launch-template 'LaunchTemplateName=cn-lt,Version=$Latest' --min-size 2 --max-size 4 --desired-capacity 2 --vpc-zone-identifier "$APP_A,$APP_B" --target-group-arns $TG_ARN --health-check-type ELB --health-check-grace-period 300
aws autoscaling put-scaling-policy --auto-scaling-group-name cn-asg --policy-name cpu-target-50 --policy-type TargetTrackingScaling --target-tracking-configuration '{"PredefinedMetricSpecification":{"PredefinedMetricType":"ASGAverageCPUUtilization"},"TargetValue":50.0}'

aws cloudwatch put-metric-alarm --alarm-name cn-high-cpu --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=AutoScalingGroupName,Value=cn-asg --statistic Average --period 300 --evaluation-periods 2 --threshold 70 --comparison-operator GreaterThanThreshold --alarm-actions $TOPIC
LB=$(echo $ALB_ARN | cut -d/ -f2-)
aws cloudwatch put-metric-alarm --alarm-name cn-alb-5xx --namespace AWS/ApplicationELB --metric-name HTTPCode_ELB_5XX_Count --dimensions Name=LoadBalancer,Value=$LB --statistic Sum --period 300 --evaluation-periods 1 --threshold 5 --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching --alarm-actions $TOPIC

echo "Website address:"
aws elbv2 describe-load-balancers --names cn-alb --query 'LoadBalancers[0].DNSName' --output text
echo "Wait 4-6 minutes until both targets are healthy."
