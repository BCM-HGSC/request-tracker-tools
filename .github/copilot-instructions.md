# Copilot Instructions for request-tracker-tools

## Project Overview
- This project is a Python package and CLI tool for interacting with RT (Request Tracker) systems, focused on secure, persistent authentication and robust ticket/attachment retrieval.
- Main code is in `src/rt_tools/`.

## Architecture & Key Components
- `src/rt_tools/cli.py`: CLI entry point. Handles argument parsing, logging, and command dispatch.
- `src/rt_tools/session.py`: Defines `RTSession`, a subclass of `requests.Session` that manages RT authentication, SSL, and cookies.
- `src/rt_tools/utils.py`: Utilities for cookie management, password/keychain access, and response parsing.
- `src/rt_tools/__init__.py`: Package init and dynamic version loading.

### Authentication & Security
- Auth uses persistent cookies (`cookies.txt`) and macOS keychain for password retrieval (via `/usr/bin/security`).
- SSL verification uses a custom cert file (`rt.hgsc.bcm.edu.pem`).
- On startup, the session loads cookies, checks auth, and re-authenticates if needed.

## Developer Workflows
- **Install (dev):**
  ```bash
  pip install -e .[dev]
  # or
  uv pip install -e .[dev]
  ```
- **Lint:**
  ```bash
  ruff check src/rt_tools/
  ruff check --fix src/rt_tools/
  ```
- **Test:**
  ```bash
  pytest
  ```
- **Run CLI:**
  ```bash
  dump-ticket 12345
  dump-ticket --verbose 12345 attachments/6789/content
  ```

## Project Conventions
- Logging levels are controlled by CLI flags: `--verbose` (DEBUG), `--quiet` (WARNING), default is INFO.
- All RT server requests go through `RTSession` for consistent auth and error handling.
- Passwords are never stored in code or config—always fetched from keychain.
- SSL cert file must be present in the working directory for secure connections.

## Integration Points
- Relies on `requests`, `keyring`, and `ruff` for core functionality and code quality.
- Uses macOS keychain and system `security` tool for credential management.
- Cookie persistence uses Mozilla cookie jar format.

## References
- See `README.md` and `CLAUDE.md` for more details and usage examples.
- Example config/setup: `pyproject.toml`, `rt.hgsc.bcm.edu.pem`, `cookies.txt`.

---

For AI agents: Always use `RTSession` for RT server access, respect logging and security conventions, and follow the CLI patterns in `cli.py`. When in doubt, check `README.md` for developer setup and workflow details.
