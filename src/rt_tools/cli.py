"""Command line interface for RT tools."""

import logging
import os
import tomllib
from argparse import ArgumentParser, Namespace
from pathlib import Path

from .downloader import download_ticket
from .session import BASE_URL, REST_URL, RTSession
from .ticket_analyzer import analyze_ticket


def analyze_ticket_cli():
    """Entry point for analyzing RT ticket data and generating automation metadata."""
    args = parse_analyze_ticket_arguments()
    config_logging(args)
    analyze_ticket(args.ticket_dir)


def download_ticket_cli():
    """Entry point for downloading complete RT ticket data."""
    args = parse_download_ticket_arguments()
    config_logging(args)

    # resolve target_dir according to resolution order
    target_dir = resolve_target_dir(args)

    with RTSession() as session:
        session.authenticate()
        if args.verbose:
            session.print_cookies()
        download_ticket(session, args.ticket_id, target_dir)


def parse_analyze_ticket_arguments() -> Namespace:
    """Parse command line arguments for analyze-ticket."""
    parser = make_parser("Analyze RT ticket data and generate automation metadata")
    parser.add_argument(
        "ticket_dir", type=Path, help="Directory containing downloaded RT ticket data"
    )
    return parser.parse_args()


def parse_download_ticket_arguments() -> Namespace:
    """Parse command line arguments for download-ticket."""
    parser = make_parser("Download complete RT ticket data to directory")
    parser.add_argument("ticket_id", help="RT ticket ID (without 'ticket/' prefix)")
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        help="Parent directory for rt{ticket_id}. "
        "Resolution order: 1. --output-dir "
        "2. $DOWNLOAD_TICKET_DIR "
        "3. config file "
        "4. current directory",
    )
    return parser.parse_args()


def resolve_target_dir(args) -> str:
    """Resolve target directory using resolution order from args."""
    # 1. Command-line option
    if args.output_dir:
        return os.path.expanduser(args.output_dir)

    # 2. Environment variable
    env_dir = os.environ.get("DOWNLOAD_TICKET_DIR")
    if env_dir:
        return os.path.expanduser(env_dir)

    # 3. Config file (~/.config/download-ticket/config.toml)
    config_path = os.path.expanduser("~/.config/download-ticket/config.toml")
    if os.path.exists(config_path):
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        default_dir = config.get("default_dir")
        if default_dir:
            return os.path.expanduser(default_dir)

    # 4. Fallback = current working directory
    return os.getcwd()


def dump_ticket():
    """Main entry point for dumping RT ticket information."""
    args = parse_dump_ticket_arguments()
    config_logging(args)
    with RTSession() as session:
        session.authenticate()
        if args.verbose:
            session.print_cookies()

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                session.dump_ticket(args.id_string, *args.parts, file=f)
        else:
            session.dump_ticket(args.id_string, *args.parts)


def parse_dump_ticket_arguments() -> Namespace:
    """Parse command line arguments."""
    parser = make_parser("Print information from an RT ticket")
    parser.add_argument("id_string", help="ID string to append to API URL")
    parser.add_argument("parts", nargs="*", help="additional path components")
    parser.add_argument(
        "-o", "--output", help="Write output to file (binary mode) instead of stdout"
    )
    return parser.parse_args()


def dump_rest():
    """Entry point for dumping content from RT REST API URLs."""
    args = parse_dump_rest_arguments()
    config_logging(args)
    with RTSession() as session:
        session.authenticate()
        if args.verbose:
            session.print_cookies()
        session.dump_rest(*args.parts)


def parse_dump_rest_arguments() -> Namespace:
    """Parse command line arguments for dump-rest."""
    parser = make_parser("Print content from an RT REST API URL")
    parser.add_argument(
        "parts", nargs="*", help=f"URL path components relative to {REST_URL}"
    )
    return parser.parse_args()


def dump_url():
    """Entry point for dumping content from arbitrary RT URLs."""
    args = parse_dump_url_arguments()
    config_logging(args)
    with RTSession() as session:
        session.authenticate()
        if args.verbose:
            session.print_cookies()
        url = "/".join([BASE_URL] + list(args.parts))
        session.dump_url(url)


def parse_dump_url_arguments() -> Namespace:
    """Parse command line arguments for dump-url."""
    parser = make_parser("Print content from an RT URL")
    parser.add_argument(
        "parts", nargs="*", help=f"URL path components relative to {BASE_URL}"
    )
    return parser.parse_args()


def make_parser(description: str) -> ArgumentParser:
    parser = ArgumentParser(description=description)
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress INFO and below messages"
    )
    return parser


def config_logging(args) -> None:
    """Configure logging based on command line arguments."""
    if args.quiet:
        log_level = logging.WARNING
    elif args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


if __name__ == "__main__":
    download_ticket_cli()
