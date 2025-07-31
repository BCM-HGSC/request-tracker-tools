#!/usr/bin/env python3

from argparse import ArgumentParser
from getpass import getuser
from subprocess import run, CalledProcessError
from sys import stderr, exit
from requests import post, RequestException
from pprint import pprint as pp

# Constants - modify these as needed
BASE_URL = "https://httpbin.org/post"
EXTERNAL_PROGRAM = "/bin/echo"
PARTIAL_EXTERNAL_COMMAND = [
    "/usr/bin/security",
    "find-generic-password",
    "-w",
    "-s",
    "foobar",
    "-a",
]
ARG1 = "argument1"
ARG2 = "argument2"


def main():
    id_string = parse_arguments()
    user = getuser()
    data = run_external_program(user)
    url = f"{BASE_URL}/{id_string}"
    url = f"{BASE_URL}"
    post_data(url, data)


def parse_arguments():
    parser = ArgumentParser(description="Submit data to API endpoint")
    parser.add_argument("id_string", help="ID string to append to base URL")
    return parser.parse_args().id_string


def run_external_program(user: str) -> str:
    try:
        command = PARTIAL_EXTERNAL_COMMAND + [user]
        response = run(command, capture_output=True, text=True, check=True)
        result = response.stdout.rstrip()
        print(repr(result))
        return result
    except CalledProcessError as e:
        print(f"External program failed with exit code {e.returncode}", file=stderr)
        print(f"Error output: {e.stderr}", file=stderr)
        exit(1)
    except FileNotFoundError:
        print(f"External program not found: {EXTERNAL_PROGRAM}", file=stderr)
        exit(1)


def post_data(url, data):
    form_data = {"arg1": ARG1, "arg2": ARG2, "data": data}
    try:
        response = post(url, data=form_data)
        response.raise_for_status()
        print(f"Successfully posted to {url}")
        print(f"Response status: {response.status_code}")
        result = response.json()
        pp(result)
    except RequestException as e:
        print(f"Failed to POST to {url}: {e}", file=stderr)
        exit(1)


if __name__ == "__main__":
    main()
