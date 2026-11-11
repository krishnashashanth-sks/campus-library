import logging
import re
import sys
from pathlib import Path


APP_VERSION = "1.0"
INSTALLED_VERSION_FILE = "library_version.txt"
_VERSION_PATTERN = re.compile(
    r"v?(\d+(?:\.\d+){1,3})",
    re.IGNORECASE,
)


def normalize_version(version):
    match = _VERSION_PATTERN.fullmatch(str(version).strip())
    if not match:
        raise ValueError(f"Unsupported application version: {version}")
    return match.group(1)


def get_app_version():
    if getattr(sys, "frozen", False):
        version_file = (
            Path(sys.executable).resolve().parent
            / INSTALLED_VERSION_FILE
        )
        try:
            return normalize_version(
                version_file.read_text(encoding="ascii")
            )
        except FileNotFoundError:
            return APP_VERSION
        except (OSError, ValueError, UnicodeError):
            logging.warning(
                "Could not read the installed application version from %s.",
                version_file,
                exc_info=True,
            )
    return APP_VERSION
