"""RT Processor package for interacting with RT (Request Tracker) systems."""

from importlib.metadata import PackageNotFoundError, version

from .session import RTSession
from .utils import dump_response, fetch_password, load_cookies, remove_fixed_string

try:
    __version__ = version("rt-processor")
except PackageNotFoundError:
    # Package is not installed, use fallback version
    __version__ = "UNKNOWN"

__all__ = [
    "RTSession",
    "dump_response",
    "fetch_password",
    "load_cookies",
    "remove_fixed_string"
]
