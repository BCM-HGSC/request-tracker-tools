"""Command line interface for RT processor."""

from argparse import ArgumentParser, Namespace

from .session import RTSession


def main():
    """Main entry point for the RT processor CLI."""
    args = parse_main_arguments()
    with RTSession() as session:
        session.authenticate()
        session.print_cookies()
        session.try_url(args.id_string, *args.parts)


def parse_main_arguments() -> Namespace:
    """Parse command line arguments."""
    parser = ArgumentParser(description="Communicate with RT")
    parser.add_argument("id_string", help="ID string to append to base URL")
    parser.add_argument("parts", nargs="*", help="additional path components")
    return parser.parse_args()


if __name__ == "__main__":
    main()
