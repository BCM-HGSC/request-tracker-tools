#!/usr/bin/env python3

import http.cookiejar as cookiejar
from argparse import ArgumentParser
from getpass import getuser
from pprint import pprint as pp
from re import IGNORECASE, match
from subprocess import CalledProcessError, run
from sys import exit, stderr

from requests import RequestException, Session

BASE_URL = "https://rt.hgsc.bcm.edu/REST/1.0/"


class RTSession(Session):
    def __init__(self):
        super().__init__()
        self.verify = "rt.hgsc.bcm.edu.pem"

    def fetch_auth_cookie(self, user: str, password: str) -> None:
        form_data = {"user": user, "pass": password}
        self.rt_post(BASE_URL, data=form_data)

    def rt_post(self, url: str, verbose=False, **kwargs) -> None:
        try:
            response = self.post(url, **kwargs)
            response.raise_for_status()
        except RequestException as e:
            print(f"Failed to POST to {url}: {e}", file=stderr)
            pp(vars(e))
            exit(1)
        else:
            if verbose:
                print_response_summary(response)

    def print_cookies(self):
        if self.cookies:
            print("Cookies received:")
            for cookie in self.cookies:
                print(f"  {cookie.name}: {cookie.value}")
        else:
            print("No cookies received")

    def check_authorized(self) -> bool:
        response = self.get(BASE_URL)
        response.raise_for_status()
        # dump_response(response)
        m = match(r"rt/[.0-9]+\s+200\sok", response.text, IGNORECASE)
        return bool(m)

    def load_cookies(self):
        cookie_file = "cookies.txt"
        cj = cookiejar.MozillaCookieJar(cookie_file)
        # Try to load existing cookies (if file exists)
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
        except FileNotFoundError:
            pass
        self.cookies = cj

    def fetch_and_save_auth_cookie(self, user, password):
        self.fetch_auth_cookie(user, password)
        self.cookies.save(ignore_discard=True, ignore_expires=True)

    def authenticate(self):
        user = getuser()
        password = fetch_password(user)
        self.fetch_and_save_auth_cookie(user, password)

    def logout(self) -> None:
        response = self.get(f"{BASE_URL}/logout")
        dump_response(response)
        self.cookies.clear()
        self.cookies.save()


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
    with RTSession() as session:
        session.fetch_auth_cookie(user, password)
        session.print_cookies()


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


def print_response_summary(response) -> None:
    print(f"Successfully posted to {response.url}")
    print(f"Response status: {response.status_code}")
    print()
    for h, v in response.headers.items():
        print(f"{h}: {v}")


def dump_response(response):
    print(response.url)
    print(response.status_code, response.reason)
    print()
    for k, v in response.headers.items():
        print(f"{k}: {v}")
    print()
    print(response.text)


if __name__ == "__main__":
    main()
