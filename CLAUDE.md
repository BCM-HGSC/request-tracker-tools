# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RT Tools is a Python package for interacting with RT (Request Tracker) systems. The project provides a command-line tool and Python library for authenticating with RT servers and querying ticket information.

## Architecture

The codebase follows a standard Python package structure with src layout:

- **`src/rt_tools/`** - Main package directory
  - **`cli.py`** - Command-line interface with argument parsing and logging configuration
  - **`session.py`** - `RTSession` class that extends `requests.Session` for RT-specific authentication and operations
  - **`downloader.py`** - `TicketDownloader` class for comprehensive ticket data download and organization
  - **`parser.py`** - Centralized RT response parsing with dataclasses and filtering logic
  - **`credentials.py`** - Password resolution across secret files and the macOS keychain, plus cookie file handling and permission enforcement
  - **`utils.py`** - Small shared helpers
  - **`__init__.py`** - Package initialization with dynamic version loading

### Key Components

**RTSession Class**: Inherits from `requests.Session` and handles:
- RT server authentication using stored cookies
- SSL certificate verification with bundled certificate (loaded from package data)
- Cookie persistence using Mozilla cookie jar format
- Authentication status checking via RT API responses

**TicketDownloader Class**: Handles comprehensive ticket data retrieval:
- Downloads ticket metadata, complete history, and all attachments
- Creates organized directory structure with individual history directories
- Uses centralized parser module for consistent data handling
- Filters outgoing emails and zero-byte attachments automatically
- Uses n-prefixed attachment naming for proper sorting (`n800.pdf`)
- Automatically converts XLSX attachments to TSV format
- Provides detailed logging of all file creation operations

**Parser Module**: Provides centralized RT response parsing:
- Defines structured dataclasses for RT data (AttachmentMeta, HistoryMessage, etc.)
- Parses attachment lists, history items, and individual messages
- Parses ticket status from `ticket/{id}` responses via `parse_ticket_status()`
- Filters outgoing emails during history parsing
- Uses string-based dataclasses to match RT API format
- Handles multi-line content and attachment extraction

**Credentials Module**: Owns every secret that touches the filesystem:
- Resolves the password in order: `--password-file` → `$RT_PASSWORD_FILE` → `~/.secrets/rt-tools/password` → `~/.secrets/rt` → macOS keychain
- Refuses to read a secret file with any group or other permission bit set
- Creates the cookie file mode 0600 inside a mode 0700 directory, before the jar writes to it
- Skips the keychain entirely where `/usr/bin/security` does not exist, so Linux hosts need no special-casing

**Authentication Flow**:
1. Attempts to load existing cookies from `~/.secrets/rt-tools/cookies.txt`
2. Checks authorization status by parsing RT server response
3. If unauthorized, resolves the password via `credentials.fetch_password()`
4. Performs authentication POST and saves new cookies with mode 0600

**Logging**: Uses Python's logging module with three levels controlled by CLI flags:
- Default: INFO level
- `--verbose`: DEBUG level (shows detailed request/response info)
- `--quiet`: WARNING level (suppresses routine messages)

## Development Commands

### Setup and Installation
```bash
# Install package in development mode with dev dependencies
uv pip install -e '.[dev]'

# Or using pip (slower)
pip install -e '.[dev]'
```

### Code Quality
```bash
# Formatting code (similar to black)
ruff format src

# Run linting (configured with pycodestyle, Pyflakes, isort, flake8-bugbear)
ruff check src/rt_tools/

# Auto-fix linting issues
ruff check --fix src/rt_tools/

# Run tests
pytest

# Run specific test modules
pytest tests/test_parser.py
pytest tests/test_ticket_downloader.py

# Run tests with verbose output
pytest -v
```

### Building and Distribution
```bash
# Build package
python -m build

# The package uses setuptools with src layout discovery
```

### Running the CLI
```bash
# The commands that talk to the REST API accept --password-file FILE in
# addition to -v/-q. open-ticket takes none of them: it opens a browser and
# never authenticates.

# Available console scripts:
download-ticket <ticket_id> [--output-dir DIR]   # Download complete RT ticket data to rt{ticket_id} subdirectory
dump-ticket <ticket_id> [additional_path_parts]  # Dump RT ticket information
dump-rest [rest_path_parts]                      # Dump content from RT REST API URLs
dump-url [url_path_parts]                        # Dump content from RT URLs
open-ticket <ticket_id>...                       # Open tickets in the web UI

# Target directory resolution (in order of priority):
# 1. --output-dir command-line option
# 2. $DOWNLOAD_TICKET_DIR environment variable
# 3. ~/.config/download-ticket/config.toml (default_dir setting)
# 4. Current working directory (fallback)

# Examples:
download-ticket 37603                           # Downloads to ./rt37603/
download-ticket 37603 --output-dir local/output # Downloads to local/output/rt37603/
export DOWNLOAD_TICKET_DIR=~/tickets && download-ticket 37603  # Downloads to ~/tickets/rt37603/

# With logging options
dump-ticket --verbose <ticket_id>   # Debug level logging
dump-ticket --quiet <ticket_id>     # Only warnings/errors
download-ticket --verbose 37603 --output-dir /tmp  # Verbose download to /tmp/rt37603/
```

## Configuration Requirements

The package expects:
- **RT Password**: available from one of the sources in the credential resolution order below
- **RT Server**: Configured to work with `https://rt.hgsc.bcm.edu/REST/1.0/` endpoint

**Note**: The SSL certificate for RT server verification is bundled as package data and loaded automatically.

### Credential Resolution

1. `--password-file FILE` command-line option
2. `$RT_PASSWORD_FILE` environment variable
3. `~/.secrets/rt-tools/password`, then `~/.secrets/rt`
4. macOS keychain, service "foobar" (skipped where `/usr/bin/security` is absent)

A file named by 1 or 2 must exist; a missing one is an error, not a fallback. Only
the first line is read and its trailing newline stripped. Secret files must be mode
0600 or 0400 — any group or other permission bit causes an error.

On macOS the keychain still works with no configuration. On Linux (notably the HPC)
create the secret file:

```bash
mkdir -m 700 -p ~/.secrets/rt-tools
chmod 600 ~/.secrets/rt-tools/password
```

Note that on an NFS-mounted HPC home directory, Unix permissions are the only
protection: storage administrators and node root can read the file. This is
acceptable for the RT password specifically, which unlocks nothing else.

### Target Directory Configuration

The `download-ticket` command supports flexible target directory configuration through multiple methods:

1. **Command-line option** (highest priority):
   ```bash
   download-ticket 37603 --output-dir /path/to/output
   ```

2. **Environment variable**:
   ```bash
   export DOWNLOAD_TICKET_DIR="~/Downloads/rt-tickets"
   download-ticket 37603  # Uses ~/Downloads/rt-tickets/
   ```

3. **Config file** (`~/.config/download-ticket/config.toml`):
   ```toml
   default_dir = "~/Documents/rt-data"
   ```

4. **Current working directory** (fallback):
   ```bash
   cd /tmp && download-ticket 37603  # Creates /tmp/rt37603/
   ```

The resolution follows this exact priority order, with higher-numbered options overriding lower-numbered ones.

## Important Implementation Details

**Parsing Architecture**: Uses centralized parser module (`parser.py`) to eliminate duplicate parsing logic. All RT responses are parsed into structured dataclasses with string attributes to match RT API format.

**Cookie Management**: Uses `http.cookiejar.MozillaCookieJar` for persistent authentication across sessions. Cookies are automatically loaded on RTSession initialization and saved after successful authentication. The jar lives at `~/.secrets/rt-tools/cookies.txt`; the session cookie is a bearer credential, so the file is created mode 0600 in a mode 0700 directory and tightened on load if found more permissive. Earlier versions used `./cookies.txt`, which is no longer read.

**Error Handling**: Authentication and request failures cause immediate program exit with error logging. The package does not implement retry logic.

**URL Construction**: RT ticket URLs are built using static methods that concatenate base URL with ticket ID and optional path components.

**Response Data**: RT REST API returns attachments surrounded by a prefix and a possible suffix. The prefix is b"RT/x.x.x 200 Ok\n\n", where x.x.x is the RT version. Anything other than this indicates an error. The suffix is present only when the URL ends with "/content/" or "/content". When present, the suffix is 3 newlines: b"\n\n\n". The three newlines never contain carraige returns. Downloading an attachment uses a content URL and requires validating the suffix and removing both suffix and prefix.

**Directory Structure**: The downloader creates an organized structure with individual history directories. The resolved target directory (from --output-dir, environment variable, config file, or current directory) is the parent directory containing multiple ticket directories:
```
resolved_target_dir/          # From resolution order: --output-dir > env var > config > cwd
├── rt37603/                  # Ticket directory (rt{ticket_id} format)
│   ├── metadata.txt          # Basic ticket information
│   ├── 1492666/              # History entry directory
│   │   ├── message.txt       # Full RT history entry (raw format)
│   │   ├── content.txt       # New content only (quoted replies stripped)
│   │   ├── n800.pdf          # Attachment with n-prefix for sorting
│   │   └── n801.xlsx         # Additional attachments
│   └── 1492934/              # Additional history entries
│       ├── message.txt
│       └── content.txt
└── rt37604/                  # Another ticket directory
    ├── metadata.txt
    └── ...
```

**File Naming Conventions**: Attachments use n-prefixed naming (`n{attachment_id}.{ext}`) to ensure proper alphabetical sorting, preventing issues where `10.pdf` would sort before `2.pdf`.

**Content Filtering**: The downloader automatically filters out:
- Outgoing emails (identified by X-RT-Loop-Prevention headers)
- Zero-byte attachments that contain no useful data
- System-generated notifications that don't contain user content

**Testing Architecture**: Comprehensive test suite with:
- Parser tests covering all parsing functions and dataclasses (14 tests)
- Downloader tests covering all methods and error scenarios (25 tests)
- Credential tests covering the resolution order, permission enforcement, and cookie file modes
- Mock fixtures for RT responses using real captured data
- Session-scoped fixtures for optimal performance
- Edge case and error handling validation

**Security**: Passwords are never stored in code or configuration files. The keychain lookup uses `["/usr/bin/security", "find-generic-password", "-w", "-s", "foobar", "-a", user]`. Where no keychain exists, the password comes from a private file under `~/.secrets`. Every secret file read or written is checked for group and other permission bits.

## RT REST API Documentation

**Primary Reference**: `docs/rt-rest-1-subset.md` - Documents only the RT REST API endpoints used by this project, including:
- Authentication endpoints and session management
- Ticket metadata retrieval (`/REST/1.0/ticket/{id}`)
- History operations (recursive fetching due to broken `format=l` parameter)
- Attachment list, metadata, and content endpoints
- Response formats and parsing requirements

**Complete Reference**: `docs/rt-rest-1-snapshot.html` - Full RT REST 1.0 API documentation snapshot for reference
