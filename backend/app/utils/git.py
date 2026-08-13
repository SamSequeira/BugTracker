import subprocess
from pathlib import Path


class GitCloneError(Exception):
    pass
def clone_repository(repository_url:str , destination: Path):
    try: 
        result = subprocess.run(["git","clone","--depth","1",repository_url,
        str(destination)], capture_output=True, text = True , timeout=300)

        if result.returncode !=0:
            error_message = result.stderr.strip()

            raise GitCloneError(
                 error_message or "Unable to clone the repository."
            )

    except subprocess.TimeoutExpired as error:
        raise GitCloneError(
            "Repository cloning timed out."
        ) from error

    except FileNotFoundError as error:
        raise GitCloneError(
            "Git is not installed or could not be found."
        ) from error

    except OSError as error:
        raise GitCloneError(
            "An operating system error occurred while cloning the repository."
        ) from error
