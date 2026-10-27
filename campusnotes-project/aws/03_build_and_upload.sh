#!/bin/bash
# Zips ../app and uploads it to S3. Also used to deploy updates (add --refresh)
set -e
source ~/vars.sh
cd "$(dirname "$0")/../app"
rm -f ~/campusnotes.zip
zip -r ~/campusnotes.zip .
[ -z "$SECRET_KEY" ] && { export SECRET_KEY=$(openssl rand -hex 32); save SECRET_KEY; }
aws s3 cp ~/campusnotes.zip s3://$BUCKET/deploy/campusnotes.zip
if [ "$1" = "--refresh" ]; then
  aws autoscaling start-instance-refresh --auto-scaling-group-name cn-asg --preferences '{"MinHealthyPercentage":50,"InstanceWarmup":120}'
fi
