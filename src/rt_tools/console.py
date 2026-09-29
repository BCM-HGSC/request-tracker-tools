"""Terminal interaction for the write commands: bodies, previews, consent.

Kept apart from writer.py, which never touches a terminal, so the rules that
decide whether RT is written to at all can be tested without a session and
without a tty.
"""

import os
import subprocess
import sys
import tempfile
from logging import getLogger
from pathlib import Path

from .writer import WriteRequest

logger = getLogger(__name__)

#: Shown at the top of the $EDITOR buffer. Lines starting with # are dropped,
#: matching git-commit, so this needs no special-casing downstream.
EDITOR_TEMPLATE = """
# Enter the message below. Lines starting with '#' are ignored, and an
# empty message aborts without writing to RT.
"""

DEFAULT_EDITOR = "vi"


class NeedsExplicitYes(RuntimeError):
    """Raised when a write cannot be confirmed because nothing is interactive."""


def resolve_body(
    message: str | None = None,
    body_file: str | os.PathLike | None = None,
    *,
    stdin=None,
) -> str:
    """Return the message body from whichever source the user supplied.

    Order: --message, then --body FILE ("-" meaning stdin), then piped stdin,
    then $EDITOR. The editor is last because it is the only source that needs
    a human present.

    Args:
        message: Value of --message, if given
        body_file: Value of --body, if given
        stdin: Overridable for testing; defaults to sys.stdin

    Returns:
        The body text, comment lines stripped when it came from the editor

    Raises:
        ValueError: If the resolved body is empty, which aborts the write
    """
    stdin = sys.stdin if stdin is None else stdin
    if message is not None:
        body = message
    elif body_file is not None:
        body = stdin.read() if str(body_file) == "-" else Path(body_file).read_text()
    elif not stdin.isatty():
        body = stdin.read()
    else:
        body = _read_from_editor()
    if not body.strip():
        raise ValueError("empty message; nothing sent")
    return body.strip("\n")


def render_preview(request: WriteRequest) -> str:
    """Render what will be sent, for --dry-run and for the confirmation prompt.

    Shows the exact content block rather than a summary of it: the whole point
    of a preview is that nothing else composes the bytes that go to RT.
    """
    endpoint = "/".join(request.parts)
    lines = [
        f"RT write: {request.summary}",
        f"endpoint: POST {endpoint}",
    ]
    if request.mails_requestors:
        lines.append("!! this sends email")
    lines.append("--- content")
    lines.append(request.content.rstrip("\n"))
    lines.append("--- end")
    return "\n".join(lines)


def confirm(request: WriteRequest, assume_yes: bool = False, *, stdin=None) -> bool:
    """Ask the user whether to send, unless they have already said so.

    Refuses rather than proceeds when there is no tty and no --yes: a script
    that silently mails requestors is the failure this guards against, and a
    prompt nobody can answer is not consent.

    Args:
        request: The write awaiting consent
        assume_yes: True when -y/--yes was given, skipping the prompt
        stdin: Overridable for testing; defaults to sys.stdin

    Returns:
        True to send, False if the user declined

    Raises:
        NeedsExplicitYes: If stdin is not interactive and --yes was not given
    """
    if assume_yes:
        return True
    stdin = sys.stdin if stdin is None else stdin
    if not stdin.isatty():
        raise NeedsExplicitYes(
            "not running interactively: pass -y/--yes to confirm this write"
        )
    print(render_preview(request))
    answer = input("Send this to RT? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def _read_from_editor() -> str:
    """Collect a message in $EDITOR, git-commit style."""
    editor = os.environ.get("EDITOR", DEFAULT_EDITOR)
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".rt.md", delete=False
    ) as handle:
        handle.write(EDITOR_TEMPLATE)
        path = Path(handle.name)
    try:
        subprocess.run([*editor.split(), str(path)], check=True)
        return strip_comments(path.read_text())
    finally:
        path.unlink(missing_ok=True)


def strip_comments(text: str) -> str:
    """Drop whole-line # comments, as git does for commit messages."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
