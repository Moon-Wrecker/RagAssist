#!/bin/bash
set -eo pipefail

echo "==> Initializing LocalStack AWS Resources..."

awslocal s3 mb s3://ragassist-docs || true
awslocal sqs create-queue --queue-name ragassist-ingest-dlq || true
awslocal sqs create-queue --queue-name ragassist-ingest --attributes '{"RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:000000000000:ragassist-ingest-dlq\",\"maxReceiveCount\":\"3\"}"}' || true

echo "==> LocalStack Initialization Completed."

