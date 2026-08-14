import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from app.services.s3_service import upload_file_to_s3


def get_repository_name(github_url: str) -> str:

    parsed_url = urlparse(github_url)

    if parsed_url.netloc.lower() not in {
        "github.com",
        "www.github.com"
    }:
        raise ValueError(
            "Only GitHub repository URLs are supported."
        )

    repository_name = Path(
        parsed_url.path.rstrip("/")
    ).name

    if repository_name.endswith(".git"):
        repository_name = repository_name[:-4]

    if not repository_name:
        raise ValueError(
            "Invalid GitHub repository URL."
        )

    return repository_name


def create_zip(
    source_directory: str,
    output_zip: str
):

    source_path = Path(source_directory)

    with zipfile.ZipFile(
        output_zip,
        "w",
        zipfile.ZIP_DEFLATED
    ) as zip_file:

        for file in source_path.rglob("*"):

            if file.is_file():

                zip_file.write(
                    file,
                    file.relative_to(source_path)
                )


def clone_and_upload_repository(
    github_url: str
):

    repository_name = get_repository_name(
        github_url
    )

    temporary_directory = tempfile.mkdtemp(
        prefix="bugtracker_"
    )

    try:

        repository_directory = os.path.join(
            temporary_directory,
            repository_name
        )

        # -----------------------------------------
        # 1. Clone GitHub repository
        # -----------------------------------------

        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                github_url,
                repository_directory
            ],
            capture_output=True,
            text=True
        )

        # -----------------------------------------
        # 2. Handle Git clone failure
        # -----------------------------------------

        if result.returncode != 0:

            git_error = (
                result.stderr.strip()
                or result.stdout.strip()
            )

            git_error_lower = git_error.lower()

            # GitHub commonly returns "Repository not found"
            # for private repositories when authentication
            # is not provided.
            if (
                "repository not found" in git_error_lower
                or "authentication failed" in git_error_lower
                or "could not read username" in git_error_lower
                or "permission denied" in git_error_lower
            ):

                raise RuntimeError(
                    "Unable to access the GitHub repository. "
                    "Please verify that the repository URL is correct "
                    "and that you have permission to access it. "
                    "Private repositories require authentication."
                )

            # Handle invalid/non-GitHub repository URLs
            if (
                "not a git repository" in git_error_lower
                or "could not resolve host" in git_error_lower
                or "unable to access" in git_error_lower
            ):

                raise RuntimeError(
                    "Unable to access the GitHub repository. "
                    "Please verify that the repository URL is correct "
                    "and that the repository is publicly accessible."
                )

            # Fallback for any other Git error
            raise RuntimeError(
                "Unable to clone the GitHub repository. "
                "Please verify the repository URL and your access permissions."
            )

        # -----------------------------------------
        # 3. Verify cloned repository exists
        # -----------------------------------------

        if not os.path.isdir(repository_directory):

            raise RuntimeError(
                "The GitHub repository could not be cloned."
            )

        # -----------------------------------------
        # 4. Create ZIP
        # -----------------------------------------

        zip_path = os.path.join(
            temporary_directory,
            f"{repository_name}.zip"
        )

        create_zip(
            repository_directory,
            zip_path
        )

        # -----------------------------------------
        # 5. Upload ZIP to S3
        # -----------------------------------------

        s3_key = (
            f"repositories/{repository_name}.zip"
        )

        upload_result = upload_file_to_s3(
            zip_path,
            s3_key
        )

        # -----------------------------------------
        # 6. Return successful result
        # -----------------------------------------

        return {
            "repository": repository_name,
            "s3_key": upload_result["key"],
            "bucket": upload_result["bucket"]
        }

    finally:

        # -----------------------------------------
        # 7. Delete temporary files
        # -----------------------------------------

        shutil.rmtree(
            temporary_directory,
            ignore_errors=True
        )