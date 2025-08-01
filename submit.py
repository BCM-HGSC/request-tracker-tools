#!/usr/bin/env python3

from argparse import ArgumentParser
from getpass import getuser
from pprint import pprint as pp
from subprocess import CalledProcessError, run
from sys import exit, stderr

from requests import RequestException, Session

# Constants - modify these as needed
# BASE_URL = "https://httpbin.org/post"
BASE_URL = "https://rt.hgsc.bcm.edu/REST/1.0/"
PARTIAL_EXTERNAL_COMMAND = [
    # "/bin/echo",
    "/usr/bin/security",
    "find-generic-password",
    "-w",
    "-s",
    "foobar",
    "-a",
]


def main():
    id_string = parse_arguments()
    user = getuser()
    data = run_external_program(user)
    url = f"{BASE_URL}/{id_string}"
    url = f"{BASE_URL}"
    with Session() as session:
        session.verify = "rt.hgsc.bcm.edu.pem"
        fetch_auth_cookie(session, url, user, data)
        print_cookies(session)


def parse_arguments():
    parser = ArgumentParser(description="Submit data to API endpoint")
    parser.add_argument("id_string", help="ID string to append to base URL")
    return parser.parse_args().id_string


def run_external_program(user: str) -> str:
    try:
        command = PARTIAL_EXTERNAL_COMMAND + [user]
        response = run(command, capture_output=True, text=True, check=True)
        result = response.stdout.rstrip()
        return result
    except CalledProcessError as e:
        print(f"External program failed with exit code {e.returncode}", file=stderr)
        print(f"Error output: {e.stderr}", file=stderr)
        exit(1)
    except FileNotFoundError:
        print(f"External program not found: {command[0]}", file=stderr)
        exit(1)


def fetch_auth_cookie(session, url, user, data):
    form_data = {"user": user, "pass": data}
    try:
        response = session.post(url, data=form_data)
        response.raise_for_status()
    except RequestException as e:
        print(f"Failed to POST to {url}: {e}", file=stderr)
        pp(vars(e))
        exit(1)
    else:
        print(f"Successfully posted to {url}")
        print(f"Response status: {response.status_code}")
        print() 
        for h, v in response.headers.items():
            print(f"{h}: {v}")


def print_cookies(session):
    if session.cookies:
        print("\nCookies received:")
        for cookie in session.cookies:
            print(f"  {cookie.name}: {cookie.value}")
    else:
        print("\nNo cookies received")


if __name__ == "__main__":
    main()
