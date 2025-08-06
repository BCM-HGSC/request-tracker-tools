"""RTSession class for handling RT authentication and requests."""

import http.cookiejar as cookiejar
from getpass import getuser
from pprint import pprint as pp
from re import IGNORECASE, match
from sys import exit

from requests import RequestException, Session

from .utils import dump_response, err, fetch_password, load_cookies

DEFAULT_COOKIE_FILE = "cookies.txt"
BASE_URL = "https://rt.hgsc.bcm.edu"
REST_URL = f"{BASE_URL}/REST/1.0/"


class RTSession(Session):
    """Session class for interacting with RT (Request Tracker) systems."""

    def __init__(self, cookie_file: str = DEFAULT_COOKIE_FILE):
        super().__init__()
        self.verify: str = "rt.hgsc.bcm.edu.pem"
        self.cookies: cookiejar.CookieJar = load_cookies(cookie_file)

    def authenticate(self) -> None:
        """Authenticate with RT if not already authenticated."""
        if self.check_authorized():
            return
        user = getuser()
        password = fetch_password(user)
        self.fetch_and_save_auth_cookie(user, password)

    def check_authorized(self) -> bool:
        """Check if the session is already authorized."""
        response = self.get(REST_URL)
        response.raise_for_status()
        m = match(r"rt/[.0-9]+\s+200\sok", response.text, IGNORECASE)
        return bool(m)

    def fetch_and_save_auth_cookie(self, user: str, password: str) -> None:
        """Fetch authentication cookie and save it."""
        form_data = {"user": user, "pass": password}
        self.rt_post(REST_URL, data=form_data)
        self.cookies.save(ignore_discard=True, ignore_expires=True)

    def rt_post(self, url: str, verbose=False, **kwargs) -> None:
        """Perform a POST request with RT-specific error handling."""
        try:
            response = self.post(url, **kwargs)
            response.raise_for_status()
        except RequestException as e:
            err(f"Failed to POST to {url}: {e}")
            pp(vars(e))
            exit(1)
        else:
            if verbose:
                dump_response(response)

    def logout(self) -> None:
        """Logout from RT and clear cookies."""
        response = self.get(f"{REST_URL}/logout")
        dump_response(response)
        self.cookies.clear()
        self.cookies.save()

    def dump_ticket(self, id_string: str, *parts) -> None:
        """Try accessing a ticket URL and dump the response."""
        self.dump_url(RTSession.ticket_url(id_string, *parts))
        # dump_response(self.get(RTSession.ticket_url(id_string, *parts)))

    def dump_url(self, url: str) -> None:
        """Try accessing a ticket URL and dump the response."""
        dump_response(self.get(url))

    def print_cookies(self) -> None:
        """Print all cookies in the session."""
        if self.cookies:
            print("Cookies received:")
            for cookie in self.cookies:
                print(f"  {cookie.name}: {cookie.value}")
        else:
            print("No cookies received")

    @staticmethod
    def ticket_url(id_string: str, *parts) -> str:
        """Generate a ticket URL with optional additional path parts."""
        return "/".join([f"{REST_URL}ticket/{id_string}"] + list(parts))
