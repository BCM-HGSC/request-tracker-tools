# RT Tools

A Python package and command-line tool for interacting with RT (Request Tracker) systems. Provides authenticated access to RT servers for querying ticket information, attachments, and other data.

## Features

- **Complete Ticket Downloads**: Download entire tickets with metadata, history, and attachments
- **Smart Attachment Processing**: Automatically skips zero-byte attachments and outgoing emails, with automatic XLSX→TSV conversion
- **Recursive History Fetching**: Handles broken RT API parameters with robust fallback methods
- **Persistent Authentication**: Automatically manages RT session cookies with secure keychain integration
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

Before using RT Tools, you need to set up:

1. **SSL Certificate**: Place `rt.hgsc.bcm.edu.pem` in your working directory for RT server verification
2. **Keychain Entry**: Store your RT password in macOS keychain with service name "foobar"
   ```bash
   security add-generic-password -s "foobar" -a "your_username" -w "your_password"
   ```

## Usage

### Command Line Interface

**`download-ticket`** - Downloads complete tickets with metadata, history, and attachments:

```bash
# Download complete ticket to local directory
download-ticket 37525 local/output

# With verbose logging to see download progress
download-ticket --verbose 37525 local/output

# With quiet mode for minimal output
download-ticket --quiet 37525 local/output
```

Features:
- Automatically skips zero-byte attachments and outgoing emails
- Uses recursive history fetching to handle broken RT API parameters
- Downloads attachments with format: `{history_id}-{attachment_id}.{extension}`
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

### Python API

```python
from rt_tools import RTSession

# Create an authenticated session
with RTSession() as session:
    session.authenticate()

    # Access ticket data programmatically
    response = session.get("https://rt.hgsc.bcm.edu/REST/1.0/ticket/37525/show")
    print(response.text)
```

## Architecture

### Core Components

- **`RTSession`**: Extends `requests.Session` with RT-specific authentication and cookie management
- **Authentication**: Automatic login using stored credentials with session persistence
- **Cookie Management**: Mozilla-format cookie jar for maintaining authentication across sessions
- **Logging**: Structured logging with configurable levels

### Authentication Flow

1. Loads existing cookies from `cookies.txt` if available
2. Checks authorization status by parsing RT server responses
3. If unauthorized, fetches password from macOS keychain
4. Performs authentication POST request and saves new cookies
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

- Passwords are stored in macOS keychain, never in code or configuration files
- SSL certificate verification prevents man-in-the-middle attacks
- Session cookies are stored locally and reused to minimize authentication requests

## Requirements

- Python 3.13+
- macOS (for keychain integration)
- Network access to RT server
- Valid RT user credentials
- SSL certificate file for RT server

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
