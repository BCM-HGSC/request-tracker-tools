"""RT Tools package for interacting with RT (Request Tracker) systems."""

from importlib.metadata import PackageNotFoundError, version

from .session import RTResponseData, RTResponseError, RTSession, parse_rt_response
from .utils import dump_response, fetch_password, load_cookies, remove_fixed_string

try:
    __version__ = version("rt-tools")
except PackageNotFoundError:
    # Package is not installed, use fallback version
    __version__ = "UNKNOWN"

__all__ = [
    "RTResponseData",
    "RTResponseError",
    "RTSession",
    "dump_response",
    "fetch_password",
    "load_cookies",
    "parse_rt_response",
    "remove_fixed_string",
]
