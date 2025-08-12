"""RT Tools package for interacting with RT (Request Tracker) systems."""

from importlib.metadata import PackageNotFoundError, version

from .downloader import TicketDownloader, download_ticket
from .session import (
    RTResponseData,
    RTResponseError,
    RTSession,
    dump_response,
    parse_rt_response,
)
from .ticket_analyzer import analyze_ticket, validate_ticket_analysis
from .utils import fetch_password, load_cookies, remove_fixed_string

try:
    __version__ = version("rt-tools")
except PackageNotFoundError:
    # Package is not installed, use fallback version
    __version__ = "UNKNOWN"

__all__ = [
    "RTResponseData",
    "RTResponseError",
    "RTSession",
    "TicketDownloader",
    "analyze_ticket",
    "download_ticket",
    "dump_response",
    "fetch_password",
    "load_cookies",
    "parse_rt_response",
    "remove_fixed_string",
    "validate_ticket_analysis",
]
