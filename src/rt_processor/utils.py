"""Utility functions for RT processor."""

import http.cookiejar as cookiejar
from subprocess import CalledProcessError, run
from sys import exit, stderr

from requests import Response

COOKIE_FILE = "cookies.txt"
PARTIAL_EXTERNAL_COMMAND = [
    "/usr/bin/security",
    "find-generic-password",
    "-w",
    "-s",
    "foobar",
    "-a",
]


def load_cookies() -> cookiejar.CookieJar:
    """Load cookies from file, creating empty jar if file doesn't exist."""
    cookie_jar = cookiejar.MozillaCookieJar(COOKIE_FILE)
    try:  # If file exists, load existing cookies
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
    except FileNotFoundError:
        pass
    return cookie_jar


def fetch_password(user: str) -> str:
    """Fetch password from keychain using security command."""
    try:
        command = PARTIAL_EXTERNAL_COMMAND + [user]
        cli_response = run(command, capture_output=True, text=True, check=True)
        result = cli_response.stdout.rstrip()
        return result
    except CalledProcessError as e:
        err(f"External program failed with exit code {e.returncode}")
        err(f"Error output: {e.stderr}")
        exit(1)
    except FileNotFoundError:
        err(f"External program not found: {command[0]}")
        exit(1)


def dump_response(response: Response) -> None:
    """Dump full response details including headers and content."""
    print(response.url)
    print(response.status_code, response.reason)
    print("-----------------")
    for k, v in response.headers.items():
        print(f"{k}: {v}")
    print("-----------------")
    print(response.text)
    print("=================")


def remove_fixed_string(multiline_string: str, fixed_string: str) -> str:
    """Remove a fixed string from each line of a multiline string."""
    lines = multiline_string.splitlines()
    cleaned_lines = [line.replace(fixed_string, '') for line in lines]
    return '\n'.join(cleaned_lines)


def err(*objects, sep=" ", end="\n", flush=False) -> None:
    """Print to stderr"""
    print(*objects, sep=sep, end=end, flush=flush, file=stderr)
