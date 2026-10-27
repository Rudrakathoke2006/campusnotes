#!/bin/bash
exec > /var/log/userdata.log 2>&1
set -x
dnf install -y python3-pip unzip amazon-efs-utils amazon-cloudwatch-agent

# EBS data volume on /data
DEV=/dev/sdf
[ -b $DEV ] || DEV=/dev/nvme1n1
for i in $(seq 1 30); do [ -b $DEV ] && break; sleep 2; done
blkid $DEV || mkfs -t xfs $DEV
mkdir -p /data
echo "UUID=$(blkid -s UUID -o value $DEV) /data xfs defaults,nofail 0 2" >> /etc/fstab
mount /data
mkdir -p /data/logs

# EFS shared storage on /mnt/efs
mkdir -p /mnt/efs
echo "__EFS__:/ /mnt/efs efs _netdev,tls 0 0" >> /etc/fstab
for i in $(seq 1 20); do mount /mnt/efs && break; sleep 15; done

# Application from S3
mkdir -p /opt/campusnotes && cd /opt/campusnotes
aws s3 cp s3://__BUCKET__/deploy/campusnotes.zip .
unzip -o campusnotes.zip
pip3 install -r requirements.txt

cat > /etc/campusnotes.env <<'ENVEOF'
AWS_REGION=ap-south-1
BUCKET=__BUCKET__
DB_HOST=__DB_HOST__
DB_SECRET=__DB_SECRET__
COGNITO_POOL_ID=__POOL__
COGNITO_CLIENT_ID=__CLIENT__
SECRET_KEY=__SECRET_KEY__
ENVEOF

cat > /etc/systemd/system/campusnotes.service <<'SVCEOF'
[Unit]
Description=CampusNotes
After=network-online.target remote-fs.target
[Service]
WorkingDirectory=/opt/campusnotes
EnvironmentFile=/etc/campusnotes.env
ExecStart=/usr/local/bin/gunicorn -w 2 -b 0.0.0.0:8000 app:app
Restart=always
[Install]
WantedBy=multi-user.target
SVCEOF

# Ship the app log to CloudWatch Logs
cat > /opt/aws/amazon-cloudwatch-agent/etc/cw.json <<'CWEOF'
{"logs":{"logs_collected":{"files":{"collect_list":[{
  "file_path":"/data/logs/app.log",
  "log_group_name":"campusnotes-app",
  "log_stream_name":"{instance_id}",
  "retention_in_days":14}]}}}}
CWEOF
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/cw.json

systemctl daemon-reload
systemctl enable --now campusnotes
