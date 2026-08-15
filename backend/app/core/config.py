import os

AWS_REGION = os.getenv(
    "AWS_REGION",
    "ap-south-1",
)

S3_BUCKET_NAME = os.getenv(
    "S3_BUCKET_NAME",
    "bugtracker-repositories-577702170996-ap-south-1-an",
)