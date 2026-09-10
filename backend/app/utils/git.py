import os
import shutil
import subprocess
from pathlib import Path


class GitCloneError(Exception):
    pass


def _find_git_executable() -> str:
    """
    Find the Git executable on Windows/Linux/macOS.
    """

    git_path = shutil.which("git")

    if git_path:
        return git_path

    # Common Git installation locations on Windows
    windows_git_paths = [
        Path(r"C:\Program Files\Git\cmd\git.exe"),
        Path(r"C:\Program Files\Git\bin\git.exe"),
        Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
        Path(r"C:\Program Files (x86)\Git\bin\git.exe"),
    ]

    for path in windows_git_paths:
        if path.exists():
            return str(path)

    raise GitCloneError(
        "Git is not installed or could not be found. "
        "Please install Git or add Git to the system PATH."
    )


def clone_repository(
    repository_url: str,
    destination: Path,
):
    try:
        git_executable = _find_git_executable()
        git_env = os.environ.copy()
        git_env["GIT_TERMINAL_PROMPT"] = "0"
        git_env["GIT_ASKPASS"] = ""

        result = subprocess.run(
            [
                git_executable,
                "clone",
                "--depth",
                "1",
                repository_url,
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=git_env,
        )

        if result.returncode != 0:

            error_message = (
                result.stderr.strip()
                or result.stdout.strip()
            )

            raise GitCloneError(
                error_message
                or "Unable to clone the repository."
            )

    except subprocess.TimeoutExpired as error:
        raise GitCloneError(
            "Repository cloning timed out."
        ) from error

    except GitCloneError:
        raise

    except OSError as error:
        raise GitCloneError(
            "An operating system error occurred while cloning "
            f"the repository: {error}"
        ) from error