"""Command line interface for RT processor."""

import logging
from argparse import ArgumentParser, Namespace

from .session import RTSession


def dump_ticket():
    """Main entry point for dumping RT ticket information."""
    args = parse_dump_ticket_arguments()

    # Determine log level based on flags
    if args.quiet:
        log_level = logging.WARNING
    elif args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    with RTSession() as session:
        session.authenticate()
        if args.verbose:
            session.print_cookies()
        session.dump_ticket(args.id_string, *args.parts)


def parse_dump_ticket_arguments() -> Namespace:
    """Parse command line arguments."""
    parser = ArgumentParser(description="Communicate with RT")
    parser.add_argument("id_string", help="ID string to append to base URL")
    parser.add_argument("parts", nargs="*", help="additional path components")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress INFO and below messages"
    )
    return parser.parse_args()


if __name__ == "__main__":
    dump_ticket()
