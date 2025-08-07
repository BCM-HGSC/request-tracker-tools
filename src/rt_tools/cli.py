"""Command line interface for RT tools."""

import logging
from argparse import ArgumentParser, Namespace

from .session import BASE_URL, REST_URL, RTSession


def dump_ticket():
    """Main entry point for dumping RT ticket information."""
    args = parse_dump_ticket_arguments()
    config_logging(args)
    with RTSession() as session:
        session.authenticate()
        if args.verbose:
            session.print_cookies()
        session.dump_ticket(args.id_string, *args.parts)


def parse_dump_ticket_arguments() -> Namespace:
    """Parse command line arguments."""
    parser = make_parser("Print information from an RT ticket")
    parser.add_argument("id_string", help="ID string to append to API URL")
    parser.add_argument("parts", nargs="*", help="additional path components")
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
    dump_ticket()
