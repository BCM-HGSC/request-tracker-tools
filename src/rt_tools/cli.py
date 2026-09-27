"""Command line interface for RT tools."""

import logging
import os
import tomllib
import webbrowser
from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from datetime import date, timedelta
from pathlib import Path
from sys import stdout

from . import __version__
from .credentials import (
    PASSWORD_FILE_CANDIDATES,
    PASSWORD_FILE_ENV_VAR,
    SECRET_FILE_MODE,
)
from .downloader import download_ticket
from .parser import TicketSummary, parse_search_results
from .session import (
    BASE_URL,
    REST_URL,
    RTSession,
    fetch_queue_names,
    search_tickets,
)

TICKET_DISPLAY_URL = f"{BASE_URL}/Ticket/Display.html?id={{}}"

QUEUE_ALIASES = {
    "mft": "Managed File Transfer",
    "sub": "Submissions",
}
SEARCH_FIELDS = "id,Subject,Status,Created,LastUpdated,Owner,Queue"
TSV_COLUMNS = (
    "id",
    "subject",
    "status",
    "created",
    "last_updated",
    "owner",
    "queue",
)


def download_ticket_cli():
    """Entry point for downloading complete RT ticket data."""
    args = parse_download_ticket_arguments()
    config_logging(args)

    # --into names the ticket directory itself; otherwise resolve the parent
    create_ticket_dir = not args.into
    if args.into:
        target_dir = os.path.expanduser(args.into)
    else:
        target_dir = resolve_target_dir(args)

    with RTSession(password_file=args.password_file) as session:
        session.authenticate()
        if args.verbose:
            session.print_cookies()
        for ticket_id in args.ticket_ids:
            try:
                download_ticket(
                    session,
                    ticket_id,
                    target_dir,
                    create_ticket_dir=create_ticket_dir,
                    transcript=args.transcript,
                    prune=args.prune,
                    lean=args.lean,
                    clean=args.clean,
                )
            except Exception as e:
                logging.error("Failed to download ticket %s: %s", ticket_id, e)


def parse_download_ticket_arguments() -> Namespace:
    """Parse command line arguments for download-ticket."""
    parser = ArgumentParser(
        description="Download complete RT ticket data to directory",
        formatter_class=RawDescriptionHelpFormatter,
        epilog="""
Output structure:
  rt{id}/
    ticket.md          chronological transcript (--transcript only)
    metadata.txt       ticket fields
    history.txt        full history listing
    attachments.txt    attachment index
    {history_id}/
      message.txt      full RT history entry (raw)
      content.txt      new content only, quoted replies stripped
                       (primary file for automated and human processing)
      n{att_id}.pdf    attachments (n-prefix for correct sort order)

With --prune, message.txt and content.txt are omitted and history
directories left empty are removed, so a {history_id}/ directory
survives only if that entry had an attachment. ticket.md is unchanged
and every path it cites still resolves.

With --lean (implies both), the unnamed text/html twins of the entry
bodies are not downloaded either, so most tickets reduce to ticket.md
plus the directories holding real attachments. ticket.md is
byte-identical across all three modes; only the files beside it differ.
It is the supported machine interface -- see docs/ticket-md-v1.md.

Downloads are otherwise additive: files from an earlier run survive even
when RT no longer has them, and re-downloading --lean over a full tree
keeps every file --lean would have skipped. -c/--clean removes those,
deleting only the filenames this tool itself writes and only after a
download that completed.
""",
    )
    add_common_arguments(parser)
    parser.add_argument("ticket_ids", nargs="+", help="One or more RT ticket IDs")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--output-dir",
        metavar="DIR",
        help="Parent directory for rt{ticket_id}. "
        "Resolution order: 1. --output-dir "
        "2. $DOWNLOAD_TICKET_DIR "
        "3. config file "
        "4. current directory",
    )
    destination.add_argument(
        "--into",
        metavar="DIR",
        help="Write the ticket contents directly into DIR, with no "
        "rt{ticket_id} level. Only valid for a single ticket ID.",
    )
    parser.add_argument(
        "--transcript",
        action="store_true",
        help="Also write ticket.md, a chronological Markdown transcript, "
        "at the top of the ticket directory",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Omit message.txt and content.txt, whose information ticket.md "
        "already carries, and remove history directories left empty. "
        "Requires --transcript.",
    )
    parser.add_argument(
        "-l",
        "--lean",
        action="store_true",
        help="Write only what ticket.md does not already carry: implies "
        "--transcript and --prune, and skips the unnamed text/html twins "
        "of the entry bodies.",
    )
    parser.add_argument(
        "-c",
        "--clean",
        action="store_true",
        help="After a complete download, delete this tool's own files that "
        "this run did not write, so re-downloading over an existing tree "
        "matches a download into an empty directory. Files the downloader "
        "never writes are left alone.",
    )
    args = parser.parse_args()
    if args.into and len(args.ticket_ids) > 1:
        parser.error("--into takes a single ticket ID; N tickets cannot share DIR")
    if args.prune and not args.transcript and not args.lean:
        parser.error("--prune requires --transcript")
    return args


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


def search_tickets_cli():
    """Entry point for searching RT tickets and writing TSV to stdout."""
    args = parse_search_arguments()
    config_logging(args)

    with RTSession(password_file=args.password_file) as session:
        session.authenticate()
        if args.verbose:
            session.print_cookies()
        queues = validate_queues(resolve_queues(args.queue), fetch_queue_names(session))
        query = build_ticket_query(args.start_date, args.end_date, queues)
        response = search_tickets(session, query, SEARCH_FIELDS)

    if not response.is_ok:
        logging.error("Search failed: RT returned %s", response.status_text)
        raise SystemExit(1)

    write_ticket_tsv(parse_search_results(response.payload))


def parse_search_arguments() -> Namespace:
    """Parse command line arguments for search-tickets."""
    alias_help = ", ".join(f"{k}={v!r}" for k, v in QUEUE_ALIASES.items())
    parser = make_parser("Search RT tickets and print a TSV summary")
    parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        type=date.fromisoformat,
        help="Earliest ticket creation date, inclusive",
    )
    parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        type=date.fromisoformat,
        help="Latest ticket creation date, inclusive",
    )
    parser.add_argument(
        "--queue",
        metavar="QUEUE",
        action="append",
        help=f"Queue to search; repeatable. Aliases: {alias_help}. "
        "Any other value is used as a literal RT queue name, matched "
        "case-insensitively and checked against the queues RT knows. "
        "Default: every alias above.",
    )
    return parser.parse_args()


def resolve_queues(queue_args: list[str] | None) -> list[str]:
    """Expand queue aliases, passing other values through as literal names."""
    if not queue_args:
        return list(QUEUE_ALIASES.values())
    return [QUEUE_ALIASES.get(q, q) for q in queue_args]


def validate_queues(queues: list[str], known_names: list[str]) -> list[str]:
    """Check queue names against RT and return them in RT's own spelling.

    Matching is case-insensitive, so "submissions" resolves to "Submissions".
    RT reports an unknown queue as zero search results rather than an error,
    so an unrecognized name is rejected here instead.

    Raises:
        SystemExit: with status 2 if any name is not a queue RT knows
    """
    by_lowered = {name.lower(): name for name in known_names}
    resolved = []
    unknown = []

    for queue in queues:
        canonical = by_lowered.get(queue.lower())
        if canonical is None:
            unknown.append(queue)
        else:
            resolved.append(canonical)

    if unknown:
        listed = ", ".join(repr(name) for name in unknown)
        logging.error("Unknown queue: %s", listed)
        logging.error("Known queues: %s", ", ".join(sorted(known_names)))
        raise SystemExit(2)

    return resolved


def build_ticket_query(
    start_date: date | None, end_date: date | None, queues: list[str]
) -> str:
    """Build the TicketSQL query for a ticket search.

    The end date is rendered as "Created < end_date + 1 day" so that tickets
    created during the named day are included despite Created being a timestamp.
    """
    queue_clause = " OR ".join(f"Queue = '{_quote(q)}'" for q in queues)
    clauses = [f"( {queue_clause} )"]

    if start_date:
        clauses.append(f"Created >= '{start_date.isoformat()}'")
    if end_date:
        day_after = end_date + timedelta(days=1)
        clauses.append(f"Created < '{day_after.isoformat()}'")

    return " AND ".join(clauses)


def write_ticket_tsv(tickets: list[TicketSummary], file=None) -> None:
    """Write ticket summaries as TSV with a header row.

    Tabs and newlines inside a field are replaced with single spaces so that
    every ticket occupies exactly one line.
    """
    if file is None:
        file = stdout
    print("\t".join(TSV_COLUMNS), file=file)
    for ticket in tickets:
        values = (getattr(ticket, column) for column in TSV_COLUMNS)
        print("\t".join(_flatten(value) for value in values), file=file)
    file.flush()


def _quote(value: str) -> str:
    """Escape single quotes for embedding in a TicketSQL string literal."""
    return value.replace("'", "''")


def _flatten(value: str) -> str:
    """Collapse tabs and line breaks to single spaces for TSV output."""
    return " ".join(value.split()) if value else ""


def dump_ticket():
    """Main entry point for dumping RT ticket information."""
    args = parse_dump_ticket_arguments()
    config_logging(args)
    with RTSession(password_file=args.password_file) as session:
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
    with RTSession(password_file=args.password_file) as session:
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
    with RTSession(password_file=args.password_file) as session:
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


def open_ticket():
    """Entry point for opening RT tickets in a browser.

    No session is created: RT's web UI handles its own authentication, and
    the browser already holds that cookie.
    """
    args = parse_open_ticket_arguments()
    for ticket_id in args.ticket_ids:
        webbrowser.open(TICKET_DISPLAY_URL.format(ticket_id))


def parse_open_ticket_arguments() -> Namespace:
    """Parse command line arguments for open-ticket."""
    parser = ArgumentParser(description="Open RT tickets in a browser")
    parser.add_argument("ticket_ids", nargs="+", help="One or more RT ticket IDs")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser.parse_args()


def make_parser(description: str) -> ArgumentParser:
    parser = ArgumentParser(description=description)
    add_common_arguments(parser)
    return parser


def add_common_arguments(parser: ArgumentParser) -> None:
    """Add the options shared by every RT tools command."""
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress INFO and below messages"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--password-file",
        metavar="FILE",
        help="File holding the RT password on its first line. "
        "Resolution order: 1. --password-file "
        f"2. ${PASSWORD_FILE_ENV_VAR} "
        f"3. {PASSWORD_FILE_CANDIDATES[0]} then {PASSWORD_FILE_CANDIDATES[1]} "
        "4. macOS keychain. "
        "Secret files must not be readable by group or other (mode "
        f"{SECRET_FILE_MODE:o} or 400).",
    )


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
