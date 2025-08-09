# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RT Tools is a Python package for interacting with RT (Request Tracker) systems. The project provides a command-line tool and Python library for authenticating with RT servers and querying ticket information.

## Architecture

The codebase follows a standard Python package structure with src layout:

- **`src/rt_tools/`** - Main package directory
  - **`cli.py`** - Command-line interface with argument parsing and logging configuration
  - **`session.py`** - `RTSession` class that extends `requests.Session` for RT-specific authentication and operations
  - **`utils.py`** - Utility functions for cookie management, password fetching, and response handling
  - **`__init__.py`** - Package initialization with dynamic version loading

### Key Components

**RTSession Class**: Inherits from `requests.Session` and handles:
- RT server authentication using stored cookies
- SSL certificate verification with custom cert file (`rt.hgsc.bcm.edu.pem`)
- Cookie persistence using Mozilla cookie jar format
- Authentication status checking via RT API responses

**Authentication Flow**: 
1. Attempts to load existing cookies from `cookies.txt`
2. Checks authorization status by parsing RT server response
3. If unauthorized, fetches password from macOS keychain using `/usr/bin/security`
4. Performs authentication POST and saves new cookies

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
```

### Building and Distribution
```bash
# Build package
python -m build

# The package uses setuptools with src layout discovery
```

### Running the CLI
```bash
# Available console scripts:
dump-ticket <ticket_id> [additional_path_parts]  # Dump RT ticket information
dump-rest [rest_path_parts]                      # Dump content from RT REST API URLs
dump-url [url_path_parts]                        # Dump content from RT URLs

# With logging options
dump-ticket --verbose <ticket_id>   # Debug level logging
dump-ticket --quiet <ticket_id>     # Only warnings/errors
```

## Configuration Requirements

The package expects:
- **SSL Certificate**: `rt.hgsc.bcm.edu.pem` file in working directory for RT server verification
- **Keychain Access**: macOS keychain entry with service "foobar" containing RT password
- **RT Server**: Configured to work with `https://rt.hgsc.bcm.edu/REST/1.0/` endpoint

## Important Implementation Details

**Cookie Management**: Uses `http.cookiejar.MozillaCookieJar` for persistent authentication across sessions. Cookies are automatically loaded on RTSession initialization and saved after successful authentication.

**Error Handling**: Authentication and request failures cause immediate program exit with error logging. The package does not implement retry logic.

**URL Construction**: RT ticket URLs are built using static methods that concatenate base URL with ticket ID and optional path components.

**Response Data**: RT REST API returns attachments surrounded by a prefix and a possible suffix. The prefix is b"RT/x.x.x 200 Ok\n\n", where x.x.x is the RT version. Anything other than this indicates an error. The suffix is present only when the URL ends with "/content/" or "/content". When present, the suffix is 3 newlines: b"\n\n\n". The three newlines never contain carraige returns. Downloading an attachment uses a content URL and requires validating the suffix and removing both suffix and prefix.

**Security**: Passwords are fetched from macOS keychain rather than being stored in code or configuration files. The keychain lookup uses partial command `["/usr/bin/security", "find-generic-password", "-w", "-s", "foobar", "-a"]` with username appended.
