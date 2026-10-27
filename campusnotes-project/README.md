# CampusNotes: AWS project files

Full step-by-step explanation is in the guide document. This folder holds every code file.

```
app/                       Flask website (this is what gets zipped and uploaded to S3)
  app.py  requirements.txt
  templates/ base.html login.html signup.html index.html
  static/style.css
stages/                    Build-from-scratch stages 1-3 (run on your laptop, see stages/README.md)
aws/
  00_setup.sh              variables file, account id, AMI
  01_network.sh            subnet IDs, DB subnets, security groups, DB subnet group
  02_services.sh EMAIL     S3 bucket, Cognito, SNS
  03_build_and_upload.sh   zip app and upload to S3 (use --refresh to redeploy)
  04_iam.sh                IAM role and instance profile for EC2
  05_efs.sh                EFS and mount targets
  06_launch.sh             launch template, ALB, Auto Scaling, alarms
  99_cleanup.sh            delete what the scripts created
  userdata.tpl             server startup script (EBS, EFS, app, CloudWatch agent)
  lifecycle.json           S3 lifecycle rule
  lambda/lambda_function.py  upload notification function
```

## Order
1. Open AWS CloudShell (region ap-south-1). Upload this folder (Actions > Upload file) and unzip it.
2. `cd campusnotes-project/aws && bash 00_setup.sh`
3. Console: VPC > Create VPC > "VPC and more" (prefix `cn`, 2 AZ, 2 public, 2 private, NAT in 1 AZ, S3 gateway endpoint).
4. `bash 01_network.sh`
5. Console: create Aurora MySQL (guide part 4). Then:
   `export DB_HOST=<writer endpoint>; save DB_HOST` and `export DB_SECRET=<secret arn>; save DB_SECRET`
6. `bash 02_services.sh you@example.com` and confirm the email.
7. Console: create the Lambda from `lambda/lambda_function.py` (guide part 5.4).
8. `bash 03_build_and_upload.sh`
9. `bash 04_iam.sh`, then `bash 05_efs.sh`, then `bash 06_launch.sh`
10. Open the printed website address after 4-6 minutes.
11. Update later: edit files in `app/`, then `bash 03_build_and_upload.sh --refresh`
12. Cleanup: `bash 99_cleanup.sh`, then the console steps it prints.

Scripts must run from the `aws` folder because they use `userdata.tpl` and `lifecycle.json` next to them.
