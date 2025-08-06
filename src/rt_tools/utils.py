"""Utility functions for RT tools."""

import http.cookiejar as cookiejar
import logging
from subprocess import CalledProcessError, run
from sys import exit, stderr

from requests import Response

logger = logging.getLogger(__name__)

PARTIAL_EXTERNAL_COMMAND = [
    "/usr/bin/security",
    "find-generic-password",
    "-w",
    "-s",
    "foobar",
    "-a",
]


def load_cookies(cookie_file: str) -> cookiejar.CookieJar:
    """Load cookies from file, creating empty jar if file doesn't exist."""
    cookie_jar = cookiejar.MozillaCookieJar(cookie_file)
    try:  # If file exists, load existing cookies
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        logger.debug(f"Loaded existing cookies from {cookie_file}")
    except FileNotFoundError:
        logger.debug(f"Cookie file {cookie_file} not found, starting with empty jar")
    return cookie_jar


def fetch_password(user: str) -> str:
    """Fetch password from keychain using security command."""
    try:
        command = PARTIAL_EXTERNAL_COMMAND + [user]
        logger.debug(f"Executing command: {' '.join(command[:3])} ...")
        cli_response = run(command, capture_output=True, text=True, check=True)
        result = cli_response.stdout.rstrip()
        logger.debug("Password fetched successfully")
        return result
    except CalledProcessError as e:
        logger.error(f"External program failed with exit code {e.returncode}")
        logger.error(f"Error output: {e.stderr}")
        exit(1)
    except FileNotFoundError:
        logger.error(f"External program not found: {command[0]}")
        exit(1)


def dump_response(response: Response) -> None:
    """Dump full response details including headers and content."""
    logger.info(f"Response URL: {response.url}")
    logger.info(f"Status: {response.status_code} {response.reason}")
    logger.debug("Response headers:")
    for k, v in response.headers.items():
        logger.debug(f"  {k}: {v}")
    print(response.text)
    print("=================")


def remove_fixed_string(multiline_string: str, fixed_string: str) -> str:
    """Remove a fixed string from each line of a multiline string."""
    lines = multiline_string.splitlines()
    cleaned_lines = [line.replace(fixed_string, "") for line in lines]
    return "\n".join(cleaned_lines)


def err(*objects, sep=" ", end="\n", flush=False) -> None:
    """Print to stderr"""
    print(*objects, sep=sep, end=end, flush=flush, file=stderr)
