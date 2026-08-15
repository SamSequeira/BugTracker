import boto3

from app.core.config import AWS_REGION, S3_BUCKET_NAME


s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION
)


def upload_file_to_s3(
    file_path: str,
    s3_key: str
):
    s3_client.upload_file(
        file_path,
        S3_BUCKET_NAME,
        s3_key
    )

    return {
        "bucket": S3_BUCKET_NAME,
        "key": s3_key
    }


def download_file_from_s3(
    s3_key: str,
    local_path: str
):
    s3_client.download_file(
        S3_BUCKET_NAME,
        s3_key,
        local_path
    )

    return local_path