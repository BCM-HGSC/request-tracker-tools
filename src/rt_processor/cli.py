"""Command line interface for RT processor."""

import logging
from argparse import ArgumentParser, Namespace

from .session import RTSession


def main():
    """Main entry point for the RT processor CLI."""
    args = parse_main_arguments()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    with RTSession() as session:
        session.authenticate()
        if args.verbose:
            session.print_cookies()
        session.try_url(args.id_string, *args.parts)


def parse_main_arguments() -> Namespace:
    """Parse command line arguments."""
    parser = ArgumentParser(description="Communicate with RT")
    parser.add_argument("id_string", help="ID string to append to base URL")
    parser.add_argument("parts", nargs="*", help="additional path components")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
