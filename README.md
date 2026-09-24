# RT Tools

A Python package and command-line tool for interacting with RT (Request Tracker) systems. Provides authenticated access to RT servers for querying ticket information, attachments, and other data.

## Features

- **Complete Ticket Downloads**: Download entire tickets with metadata, complete history, individual history items, and attachments
- **Smart Attachment Processing**: Automatically skips zero-byte attachments and outgoing emails, with automatic XLSX→TSV conversion
- **Recursive History Fetching**: Handles broken RT API parameters with robust fallback methods
- **Persistent Authentication**: Automatically manages RT session cookies, stored privately under `~/.secrets/rt-tools/`
- **Portable Credentials**: Reads the RT password from a `~/.secrets` file on Linux (including the HPC) or the macOS keychain
- **SSL Certificate Verification**: Custom certificate support for secure RT server connections
- **Flexible Logging**: Configurable log levels (quiet, normal, verbose) for debugging and production use
- **Command-line Interface**: Multiple CLI tools for accessing RT ticket data and attachments

## Installation

### Development Installation
```bash
# Clone the repository
git clone <repository-url>
cd rt-tools

# Install in development mode with dev dependencies
pip install -e .[dev]

# Or using uv
uv pip install -e .[dev]
```

### Production Installation
```bash
pip install rt-tools
```

**Note**: The package includes `openpyxl` for automatic XLSX→TSV conversion of Excel attachments.

## Configuration

Before using RT Tools, you need to make your RT password available through one of
the sources below. RT Tools consults them in this order and uses the first one it
finds:

1. **`--password-file FILE`** command-line option (highest priority)
2. **`$RT_PASSWORD_FILE`** environment variable
3. **Secret file**: `~/.secrets/rt-tools/password`, then `~/.secrets/rt`
4. **macOS keychain**, service name "foobar" (only where `/usr/bin/security` exists)

A file named by option 1 or 2 must exist; a missing one is an error rather than a
reason to fall through to a later source.

### Secret file (Linux, including the HPC)

```bash
mkdir -m 700 -p ~/.secrets/rt-tools
touch ~/.secrets/rt-tools/password
chmod 600 ~/.secrets/rt-tools/password
# then put the password on the first line
```

Only the first line is read, and its trailing newline is stripped. RT Tools
**refuses to read a secret file that has any group or other permission bit set**
— use mode 600 or 400.

### macOS keychain

```bash
security add-generic-password -s "foobar" -a "your_username" -w "your_password"
```

### Cookie file

Session cookies are written to `~/.secrets/rt-tools/cookies.txt`, in a directory
created mode 700 with the file created mode 600. The cookie is a bearer
credential, so it is treated as a secret in its own right. Earlier versions wrote
`cookies.txt` into the current working directory; that file is no longer used and
can be deleted.

**Note**: The SSL certificate for RT server verification is bundled with the package and requires no manual setup.

## Usage

### Command Line Interface

**`download-ticket`** - Downloads complete tickets with metadata, history, and attachments:

```bash
# Download ticket to current directory (creates ./rt37525/)
download-ticket 37525

# Download to specific directory (creates local/output/rt37525/)
download-ticket 37525 --output-dir local/output

# Download multiple tickets (authenticate once, loop sequentially)
download-ticket 37525 37526 37527

# From clipboard or file via xargs
pbpaste | xargs download-ticket
cat tickets.txt | xargs download-ticket

# With verbose logging to see download progress
download-ticket --verbose 37525

# With quiet mode for minimal output
download-ticket --quiet 37525 --output-dir /tmp

# With an explicit password file (all four commands accept this)
download-ticket 37525 --password-file ~/.secrets/rt-tools/password
```

**Target Directory Resolution**:
The `download-ticket` command resolves the output directory in the following order:
1. `--output-dir` command-line option (highest priority)
2. `$DOWNLOAD_TICKET_DIR` environment variable
3. `~/.config/download-ticket/config.toml` config file (`default_dir` setting)
4. Current working directory (fallback)

```bash
# Environment variable example
export DOWNLOAD_TICKET_DIR="~/Downloads/rt-tickets"
download-ticket 37525  # Creates ~/Downloads/rt-tickets/rt37525/

# Config file example (~/.config/download-ticket/config.toml)
# default_dir = "~/Documents/rt-data"
download-ticket 37525  # Creates ~/Documents/rt-data/rt37525/
```

**Directory Structure**:
```
output_directory/         # Resolved from --output-dir, env var, config, or cwd
└── rt37525/              # Ticket directory (rt{ticket_id} format)
    ├── metadata.txt      # Ticket basic information
    ├── history.txt       # Complete ticket history
    ├── attachments.txt   # Attachment index
    ├── 456/              # History entry directory
    │   ├── message.txt   # Full RT history entry (raw format)
    │   └── content.txt   # New content only — quoted replies stripped
    ├── 458/              # Another history entry directory
    │   ├── message.txt
    │   ├── content.txt
    │   ├── n800.pdf      # Attachment for this history entry
    │   └── n801.xlsx     # Also saved as n801.tsv (auto-converted)
    └── ...
```

Features:
- **Organized structure**: Each history entry and its attachments are grouped in individual directories
- **Consistent filtering**: Automatically skips zero-byte attachments and outgoing emails from both attachments and individual history items
- Uses recursive history fetching to handle broken RT API parameters
- Downloads attachments with format: `n{attachment_id}.{extension}` within each history directory (the "n" prefix ensures message.txt sorts first)
- **Individual history items**: Each history entry is saved as `{history_id}/message.txt` (full raw entry) and `{history_id}/content.txt` (new content only, with quoted replies stripped). `content.txt` is the primary file for automated and human processing.
- **Automatic XLSX→TSV conversion**: Excel files are automatically converted to tab-separated values for easier analysis
- Creates comprehensive ticket metadata and history files

**`dump-ticket`** - Retrieves and displays RT ticket information:

```bash
# Basic ticket information
dump-ticket 37525

# Ticket with additional path components (e.g., attachments)
dump-ticket 37525 attachments/1483996/content

# With verbose logging (shows authentication details, headers, etc.)
dump-ticket --verbose 37525

# With quiet mode (only errors and warnings)
dump-ticket --quiet 37525
```

**`dump-rest`** - Retrieves content from RT REST API URLs (relative to REST/1.0 endpoint):

```bash
# List all tickets
dump-rest

# Show specific ticket
dump-rest ticket/37525/show

# Access ticket attachments
dump-rest ticket/37525/attachments

# With logging options
dump-rest --verbose ticket/37525/show
dump-rest --quiet user/username
```

**`dump-url`** - Retrieves content from arbitrary RT URLs (relative to server base):

```bash
# Access REST API directly
dump-url REST/1.0/

# Access specific RT paths
dump-url NoAuth/css/base/main.css

# With logging options
dump-url --verbose REST/1.0/ticket/37525/show
dump-url --quiet some/path
```

**`open-ticket`** - Opens tickets in the web UI. Unlike the other commands it
creates no session and needs no password: the browser already holds RT's
cookie.

```bash
# Open one ticket
open-ticket 37525

# Open several at once
open-ticket 37525 37526
```

### Python API

```python
from rt_tools import RTSession, get_ticket_statuses

# Create an authenticated session
with RTSession() as session:
    session.authenticate()

    # Check status of one or more tickets
    statuses = get_ticket_statuses(["37525", "37526"], session)
    # {"37525": "open", "37526": "resolved"}

    # Access ticket data programmatically
    response = session.get("https://rt.hgsc.bcm.edu/REST/1.0/ticket/37525")
    print(response.text)
```

**`get_ticket_statuses(ticket_ids, session)`** fetches ticket status via the REST API and
returns a dict mapping each ticket ID to `"open"` (new/open/stalled), `"resolved"`, or
`"unknown"`.

## Architecture

### Core Components

- **`RTSession`**: Extends `requests.Session` with RT-specific authentication and cookie management
- **Authentication**: Automatic login using stored credentials with session persistence
- **`credentials`**: Resolves the password across secret files and the keychain, and enforces private permissions on every secret it reads or writes
- **Cookie Management**: Mozilla-format cookie jar for maintaining authentication across sessions
- **Logging**: Structured logging with configurable levels

### Authentication Flow

1. Loads existing cookies from `~/.secrets/rt-tools/cookies.txt` if available
2. Checks authorization status by parsing RT server responses
3. If unauthorized, resolves the password from a secret file or the macOS keychain
4. Performs authentication POST request and saves new cookies mode 600
5. Subsequent requests use stored authentication cookies

### URL Construction

RT URLs are constructed as: `BASE_URL/ticket/{id}/{path_components...}`

- Base URL: `https://rt.hgsc.bcm.edu/REST/1.0/`
- Ticket ID: Numeric identifier (e.g., `37525`)
- Path components: Optional additional paths (e.g., `attachments/1483996/content`)

## Development

### Code Quality
```bash
# Run linting
ruff check src/rt_tools/

# Auto-fix issues
ruff check --fix src/rt_tools/

# Run tests
pytest

# Install pre-commit hooks (one-time setup)
uv pip install pre-commit
pre-commit install

# Run pre-commit on all files
pre-commit run --all-files
```

Pre-commit hooks are configured to run:
- Ruff linting and formatting
- MyPy type checking
- Basic file hygiene (trailing whitespace, end-of-file fixes)
- YAML/TOML validation
- Large file detection

Binary test fixtures (`.bin` files) are excluded from text processing hooks.

### Building
```bash
# Build package
python -m build
```

## Logging Levels

- **Default (INFO)**: Shows basic operation status and responses
- **Verbose (DEBUG)**: Shows detailed request/response information, headers, authentication steps
- **Quiet (WARNING)**: Shows only warnings and errors, suppresses routine operational messages

## Security

- Passwords are never stored in code or configuration files — they come from the macOS keychain or a private file under `~/.secrets`
- Secret files must be mode 600 or 400; a file readable by group or other is rejected with an error
- Cookie files are created mode 600 in a mode 700 directory, and tightened on load if they are found to be more permissive
- SSL certificate verification prevents man-in-the-middle attacks
- Session cookies are stored locally and reused to minimize authentication requests

On a shared filesystem such as an NFS-mounted HPC home directory, Unix permissions
are the only barrier protecting a secret file. Storage administrators and node root
can read it. Use this mechanism only for credentials where that exposure is
acceptable.

## Requirements

- Python 3.13+
- macOS or Linux (the keychain is used on macOS; Linux uses a `~/.secrets` file)
- Network access to RT server
- Valid RT user credentials

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
