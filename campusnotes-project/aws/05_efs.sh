#!/bin/bash
set -e
source ~/vars.sh
export EFS=$(aws efs create-file-system --encrypted --performance-mode generalPurpose --throughput-mode elastic --tags Key=Name,Value=cn-efs --query FileSystemId --output text); save EFS
until [ "$(aws efs describe-file-systems --file-system-id $EFS --query 'FileSystems[0].LifeCycleState' --output text)" = available ]; do sleep 5; done
aws efs create-mount-target --file-system-id $EFS --subnet-id $APP_A --security-groups $EFS_SG
aws efs create-mount-target --file-system-id $EFS --subnet-id $APP_B --security-groups $EFS_SG
echo "EFS $EFS ready. Next: 06_launch.sh"
