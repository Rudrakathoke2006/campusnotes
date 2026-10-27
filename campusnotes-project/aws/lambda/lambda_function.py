import boto3, os

sns = boto3.client('sns')


def lambda_handler(event, context):
    for r in event['Records']:
        key = r['s3']['object']['key']
        size = r['s3']['object']['size']
        sns.publish(
            TopicArn=os.environ['TOPIC_ARN'],
            Subject='CampusNotes: new note uploaded',
            Message='File %s (%s bytes) was uploaded.' % (key, size))
