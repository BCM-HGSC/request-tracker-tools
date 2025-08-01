#!/usr/bin/env python3

from argparse import ArgumentParser
from getpass import getuser
from pprint import pprint as pp
from subprocess import CalledProcessError, run
from sys import exit, stderr

from requests import RequestException, Session

BASE_URL = "https://rt.hgsc.bcm.edu/REST/1.0/"
PARTIAL_EXTERNAL_COMMAND = [
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
    password = fetch_password(user)
    url = f"{BASE_URL}ticket/{id_string}/show"
    with Session() as session:
        session.verify = "rt.hgsc.bcm.edu.pem"
        fetch_auth_cookie(session, BASE_URL, user, password)
        print_cookies(session)


def parse_arguments() -> str:
    parser = ArgumentParser(description="Communicate with RT")
    parser.add_argument("id_string", help="ID string to append to base URL")
    return parser.parse_args().id_string


def fetch_password(user: str) -> str:
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


def fetch_auth_cookie(session: Session, user: str, password: str) -> None:
    form_data = {"user": user, "pass": password}
    post(session, BASE_URL, data=form_data)


def post(session: Session, url: str, verbose=False, **kwargs) -> None:
    try:
        response = session.post(url, **kwargs)
        response.raise_for_status()
    except RequestException as e:
        print(f"Failed to POST to {url}: {e}", file=stderr)
        pp(vars(e))
        exit(1)
    else:
        if verbose:
            print_response_summary(response)


def print_response_summary(response) -> None:
    print(f"Successfully posted to {response.url}")
    print(f"Response status: {response.status_code}")
    print() 
    for h, v in response.headers.items():
        print(f"{h}: {v}")


def print_cookies(session: Session):
    if session.cookies:
        print("Cookies received:")
        for cookie in session.cookies:
            print(f"  {cookie.name}: {cookie.value}")
    else:
        print("No cookies received")


if __name__ == "__main__":
    main()
