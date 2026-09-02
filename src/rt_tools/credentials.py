"""Credential and secret-file handling for RT tools.

Secrets live under ``~/.secrets`` following a one-file-per-secret convention:
the directory is mode 0700 and each file is mode 0600 (or 0400). Files that are
readable by group or other are rejected rather than used.

The macOS keychain remains the last resort in the resolution order, so a
MacBook needs no secret file while Linux hosts (notably the HPC, where there is
no keychain) need no special-casing beyond dropping a file in place.
"""

import http.cookiejar as cookiejar
import logging
import os
import stat
from pathlib import Path
from subprocess import CalledProcessError, run
from sys import exit

logger = logging.getLogger(__name__)

SECRETS_DIR = Path("~/.secrets/rt-tools")
DEFAULT_COOKIE_FILE = SECRETS_DIR / "cookies.txt"
PASSWORD_FILE_ENV_VAR = "RT_PASSWORD_FILE"
PASSWORD_FILE_CANDIDATES = (SECRETS_DIR / "password", Path("~/.secrets/rt"))
KEYCHAIN_COMMAND = "/usr/bin/security"
KEYCHAIN_SERVICE = "foobar"
SECRET_DIR_MODE = 0o700
SECRET_FILE_MODE = 0o600
GROUP_AND_OTHER = stat.S_IRWXG | stat.S_IRWXO


# Password resolution


def fetch_password(user: str, password_file: str | os.PathLike | None = None) -> str:
    """Fetch the RT password using the credential resolution order.

    1. ``password_file`` argument (``--password-file``)
    2. ``$RT_PASSWORD_FILE``
    3. ``~/.secrets/rt-tools/password``, then ``~/.secrets/rt``
    4. macOS keychain (only where ``/usr/bin/security`` exists)

    Exits with an error if no source yields a password.
    """
    path = resolve_password_file(password_file)
    if path is not None:
        return read_secret_file(path)
    if keychain_available():
        return fetch_password_from_keychain(user)
    logger.error(
        "No RT password available. Create %s (mode %o) or pass --password-file.",
        expand(PASSWORD_FILE_CANDIDATES[0]),
        SECRET_FILE_MODE,
    )
    exit(1)


def resolve_password_file(
    password_file: str | os.PathLike | None = None,
) -> Path | None:
    """Return the password file to use, or None to fall through to the keychain.

    An explicitly requested file that does not exist is an error rather than a
    reason to fall back to a different source.
    """
    for source, value in (
        ("--password-file", password_file),
        (f"${PASSWORD_FILE_ENV_VAR}", os.environ.get(PASSWORD_FILE_ENV_VAR)),
    ):
        if value:
            path = expand(value)
            if not path.is_file():
                logger.error(f"Password file from {source} not found: {path}")
                exit(1)
            return path

    for candidate in PASSWORD_FILE_CANDIDATES:
        path = expand(candidate)
        if path.is_file():
            return path

    return None


def read_secret_file(path: Path) -> str:
    """Read a single-line secret from a file, rejecting over-permissive modes."""
    check_secret_mode(path)
    with open(path, encoding="utf-8") as f:
        secret = f.readline().rstrip("\r\n")
    if not secret:
        logger.error(f"Secret file is empty: {path}")
        exit(1)
    logger.debug(f"Secret read from {path}")
    return secret


def check_secret_mode(path: Path) -> None:
    """Exit if a secret file is readable by group or other."""
    mode = path.stat().st_mode
    if mode & GROUP_AND_OTHER:
        logger.error(
            f"Permissions {stat.filemode(mode)} on {path} are too open. "
            f"Fix with: chmod {SECRET_FILE_MODE:o} {path}"
        )
        exit(1)


def keychain_available() -> bool:
    """Report whether the macOS keychain command is present."""
    return os.path.exists(KEYCHAIN_COMMAND)


def fetch_password_from_keychain(user: str) -> str:
    """Fetch the password from the macOS keychain."""
    command = [
        KEYCHAIN_COMMAND,
        "find-generic-password",
        "-w",
        "-s",
        KEYCHAIN_SERVICE,
        "-a",
        user,
    ]
    try:
        logger.debug(f"Executing command: {' '.join(command[:3])} ...")
        cli_response = run(command, capture_output=True, text=True, check=True)
    except CalledProcessError as e:
        logger.error(f"External program failed with exit code {e.returncode}")
        logger.error(f"Error output: {e.stderr}")
        exit(1)
    except FileNotFoundError:
        logger.error(f"External program not found: {command[0]}")
        exit(1)
    logger.debug("Password fetched successfully")
    return cli_response.stdout.rstrip()


# Cookie file handling


def load_cookies(cookie_file: str | os.PathLike) -> cookiejar.CookieJar:
    """Load cookies from file, creating empty jar if file doesn't exist."""
    path = expand(cookie_file)
    cookie_jar = cookiejar.MozillaCookieJar(str(path))
    try:
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
    except FileNotFoundError:
        logger.debug(f"Cookie file {path} not found, starting with empty jar")
    else:
        logger.debug(f"Loaded existing cookies from {path}")
        restrict_secret_mode(path)
    return cookie_jar


def save_cookies(cookie_jar: cookiejar.MozillaCookieJar) -> None:
    """Save cookies to a file that only the owner can read.

    A session cookie is a bearer credential, so the file is created with mode
    0600 before the jar writes to it rather than being tightened afterwards.
    """
    path = Path(cookie_jar.filename)
    path.parent.mkdir(mode=SECRET_DIR_MODE, parents=True, exist_ok=True)
    create_secret_file(path)
    cookie_jar.save(ignore_discard=True, ignore_expires=True)
    restrict_secret_mode(path)


def create_secret_file(path: Path) -> None:
    """Create an empty file with mode 0600 if it does not already exist."""
    os.close(os.open(path, os.O_CREAT | os.O_WRONLY, SECRET_FILE_MODE))


def restrict_secret_mode(path: Path) -> None:
    """Tighten a file we own to mode 0600, warning if it was readable."""
    mode = path.stat().st_mode
    if mode & GROUP_AND_OTHER:
        logger.warning(
            f"Permissions {stat.filemode(mode)} on {path} are too open; "
            f"tightening to {SECRET_FILE_MODE:o}"
        )
    if stat.S_IMODE(mode) != SECRET_FILE_MODE:
        path.chmod(SECRET_FILE_MODE)


# Utilities


def expand(path: str | os.PathLike) -> Path:
    """Expand a user-supplied path, resolving a leading ``~``."""
    return Path(path).expanduser()
