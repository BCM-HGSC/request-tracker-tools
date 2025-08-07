"""RTSession class for handling RT authentication and requests."""

import http.cookiejar as cookiejar
from getpass import getuser
from pprint import pprint as pp
from re import IGNORECASE, match
from sys import exit

from requests import RequestException, Response, Session

from .utils import dump_response, err, fetch_password, load_cookies

DEFAULT_COOKIE_FILE = "cookies.txt"
BASE_URL = "https://rt.hgsc.bcm.edu"
REST_URL = f"{BASE_URL}/REST/1.0"


class RTResponseError(ValueError):
    """Exception raised when RT API response format is invalid or unexpected."""

    def __init__(self, message: str, response: Response = None):
        super().__init__(message)
        self.response = response


def validate_rt_response(response: Response) -> None:
    """Validate RT API response format and raise RTResponseError if invalid.

    RT responses should start with b"RT/x.x.x 200 Ok\n\n" pattern.
    This function checks for acceptable RT response prefixes.

    Args:
        response: The requests.Response object to validate

    Raises:
        RTResponseError: If response doesn't match expected RT format
    """
    if not response.content:
        raise RTResponseError("Empty response content", response)

    # Check for valid RT response prefix pattern
    # Pattern: RT/{version} {status_code} {status_text}\n\n
    if not match(rb"^RT/[\d.]+\s+\d+\s+[^\r\n]+\r?\n\r?\n", response.content):
        # Get first 50 bytes for error message to avoid exposing full content
        prefix = response.content[:50]
        raise RTResponseError(
            f"Invalid RT response format. Expected 'RT/x.x.x status message\\n\\n' "
            f"but got: {prefix!r}",
            response
        )


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
        response = self.get(BASE_URL)
        response.raise_for_status()
        m = match(r"rt/[.0-9]+\s+200\sok", response.text, IGNORECASE)
        return bool(m)

    def fetch_and_save_auth_cookie(self, user: str, password: str) -> None:
        """Fetch authentication cookie and save it."""
        form_data = {"user": user, "pass": password}
        self.rt_post(BASE_URL, data=form_data)
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
        """GET a ticket URL and dump the response."""
        self.dump_url(RTSession.ticket_url(id_string, *parts))

    def dump_rest(self, *parts) -> None:
        """GET a REST 1.0 URL and dump the response."""
        url = RTSession.rest_url(*parts)
        response = self.get(url)
        validate_rt_response(response)
        dump_response(response)

    def dump_url(self, url: str) -> None:
        """GET a URL and dump the response."""
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
        return RTSession.rest_url("ticket", id_string, *parts)

    @staticmethod
    def rest_url(*parts) -> str:
        """Generate a REST 1.0 URL using any supplied parts."""
        return "/".join([REST_URL] + list(parts))
