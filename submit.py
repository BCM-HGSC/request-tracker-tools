#!/usr/bin/env python3

import http.cookiejar as cookiejar
from argparse import ArgumentParser
from getpass import getuser
from pprint import pprint as pp
from re import IGNORECASE, match
from subprocess import CalledProcessError, run
from sys import exit, stderr

from requests import Response, RequestException, Session

COOKIE_FILE = "cookies.txt"
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
    # url = f"{BASE_URL}ticket/{id_string}/show"
    user = getuser()
    password = fetch_password(user)
    with RTSession() as session:
        session.fetch_auth_cookie(user, password)
        session.print_cookies()


def parse_arguments() -> str:
    parser = ArgumentParser(description="Communicate with RT")
    parser.add_argument("id_string", help="ID string to append to base URL")
    return parser.parse_args().id_string


class RTSession(Session):
    def __init__(self):
        super().__init__()
        self.verify: str = "rt.hgsc.bcm.edu.pem"
        self.cookies: cookiejar.CookieJar = load_cookies()

    def authenticate(self):
        if self.check_authorized():
            return
        user = getuser()
        password = fetch_password(user)
        self.fetch_and_save_auth_cookie(user, password)

    def check_authorized(self) -> bool:
        response = self.get(BASE_URL)
        response.raise_for_status()
        # dump_response(response)
        m = match(r"rt/[.0-9]+\s+200\sok", response.text, IGNORECASE)
        return bool(m)

    def fetch_and_save_auth_cookie(self, user: str, password: str) -> None:
        form_data = {"user": user, "pass": password}
        self.rt_post(BASE_URL, data=form_data)
        self.cookies.save(ignore_discard=True, ignore_expires=True)

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
                dump_response(response)

    def logout(self) -> None:
        response = self.get(f"{BASE_URL}/logout")
        dump_response(response)
        self.cookies.clear()
        self.cookies.save()

    def print_cookies(self):
        if self.cookies:
            print("Cookies received:")
            for cookie in self.cookies:
                print(f"  {cookie.name}: {cookie.value}")
        else:
            print("No cookies received")


def load_cookies() -> cookiejar.CookieJar:
    cookie_jar = cookiejar.MozillaCookieJar(COOKIE_FILE)
    try:  # If file exists, load existing cookies
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
    except FileNotFoundError:
        pass
    return cookie_jar


def fetch_password(user: str) -> str:
    try:
        command = PARTIAL_EXTERNAL_COMMAND + [user]
        cli_response = run(command, capture_output=True, text=True, check=True)
        result = cli_response.stdout.rstrip()
        return result
    except CalledProcessError as e:
        print(f"External program failed with exit code {e.returncode}", file=stderr)
        print(f"Error output: {e.stderr}", file=stderr)
        exit(1)
    except FileNotFoundError:
        print(f"External program not found: {command[0]}", file=stderr)
        exit(1)


def dump_response(response: Response):
    print(response.url)
    print(response.status_code, response.reason)
    print()
    for k, v in response.headers.items():
        print(f"{k}: {v}")
    print()
    print(response.text)


if __name__ == "__main__":
    main()
