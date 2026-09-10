import os
import tempfile
import pytest
import boto3

from app.core.config import AWS_REGION, S3_BUCKET_NAME, s3_config
from app.services.s3_service import (
    upload_file_to_s3,
    download_file_from_s3,
)

s3_available = bool(s3_config.enabled and s3_config.access_key_id and s3_config.secret_access_key)


# --------------------------------------------------
# 1. Test S3 connection
# --------------------------------------------------

@pytest.mark.skipif(not s3_available, reason="AWS S3 credentials or bucket not configured")
def test_s3_connection():

    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION
    )

    s3.head_bucket(
        Bucket=S3_BUCKET_NAME
    )

    print("\nS3 connection successful!")
    print("Bucket:", S3_BUCKET_NAME)


# --------------------------------------------------
# 2. Test upload and download
# --------------------------------------------------

@pytest.mark.skipif(not s3_available, reason="AWS S3 credentials or bucket not configured")
def test_s3_upload_download():

    test_s3_key = "tests/test_s3_file.txt"

    # Create a temporary test file
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        suffix=".txt"
    ) as temp_file:

        temp_file.write(
            "BugTracker S3 test file."
        )

        local_file = temp_file.name

    downloaded_file = None
    s3 = None

    try:

        # Upload
        try:
            upload_result = upload_file_to_s3(
                local_file,
                test_s3_key
            )
        except Exception as exc:
            if "AccessDenied" in str(exc) or "403" in str(exc):
                pytest.skip(f"AWS IAM user lacks s3:PutObject permissions on {S3_BUCKET_NAME}")
            raise

        print("\nUpload successful!")
        print(upload_result)

        # Check object exists in S3
        s3 = boto3.client(
            "s3",
            region_name=AWS_REGION
        )

        s3.head_object(
            Bucket=S3_BUCKET_NAME,
            Key=test_s3_key
        )

        print("S3 object verified!")

        # Download
        downloaded_file = tempfile.mktemp(
            suffix=".txt"
        )

        download_file_from_s3(
            test_s3_key,
            downloaded_file
        )

        # Verify downloaded content
        with open(
            downloaded_file,
            "r"
        ) as file:

            content = file.read()

        assert content == "BugTracker S3 test file."

        print("Download successful!")
        print("Downloaded content verified!")

    finally:

        # Delete test object from S3 if client was created
        if s3 is not None:
            try:
                s3.delete_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=test_s3_key
                )
                print("Test S3 object deleted.")
            except Exception:
                pass

        # Delete local temporary files
        if os.path.exists(local_file):
            os.remove(local_file)

        if downloaded_file and os.path.exists(downloaded_file):
            os.remove(downloaded_file)


# --------------------------------------------------
# Run tests directly
# --------------------------------------------------

if __name__ == "__main__":

    test_s3_connection()

    test_s3_upload_download()

    print("\nAll S3 tests passed successfully!")