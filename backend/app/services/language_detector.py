from pathlib import Path


LANGUAGE_EXTENSIONS = {
    ".py": "Python",
    ".java": "Java",
    ".js": "JavaScript",
}


def detect_language(filename: str) -> str:
    """
    Detect programming language from a file name/path.
    """

    extension = Path(filename).suffix.lower()

    return LANGUAGE_EXTENSIONS.get(extension, "Unsupported")


def is_supported_file(filename: str) -> bool:
    """
    Check whether the file is supported by the bug tracking system.
    """

    extension = Path(filename).suffix.lower()

    return extension in LANGUAGE_EXTENSIONS