#!/usr/bin/env python3
"""
Chrome Cookie Extractor
Extracts cookies for a specified domain from Chrome's cookie database
and outputs them in TSV format (domain, name, value).
"""

import sqlite3
import os
import sys
import argparse
import platform
from pathlib import Path
import csv


def get_chrome_cookie_path():
    """Get the path to Chrome's cookie database based on the operating system."""
    system = platform.system()
    
    if system == "Windows":
        # Windows path
        base_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default")
    elif system == "Darwin":  # macOS
        # macOS path
        base_path = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default")
    elif system == "Linux":
        # Linux path
        base_path = os.path.expanduser("~/.config/google-chrome/Default")
    else:
        raise OSError(f"Unsupported operating system: {system}")
    
    cookie_path = os.path.join(base_path, "Cookies")
    
    if not os.path.exists(cookie_path):
        raise FileNotFoundError(f"Chrome cookie database not found at: {cookie_path}")
    
    return cookie_path


def extract_cookies(domain, cookie_db_path):
    """Extract cookies for the specified domain from Chrome's cookie database."""
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(cookie_db_path)
        cursor = conn.cursor()
        
        # Query cookies for the specified domain
        # Using LIKE to match subdomains as well
        query = """
        SELECT host_key, name, value 
        FROM cookies 
        WHERE host_key LIKE ?
        ORDER BY host_key, name
        """
        
        # Add wildcards to match the domain and its subdomains
        domain_pattern = f"%{domain}%"
        
        cursor.execute(query, (domain_pattern,))
        cookies = cursor.fetchall()
        
        conn.close()
        return cookies
        
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error accessing cookie database: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Extract cookies from Chrome for a specified domain and output as TSV"
    )
    parser.add_argument(
        "domain", 
        help="Domain to extract cookies for (e.g., example.com)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file (default: stdout)",
        default=None
    )
    
    args = parser.parse_args()
    
    try:
        # Get Chrome cookie database path
        cookie_db_path = get_chrome_cookie_path()
        
        # Extract cookies for the domain
        cookies = extract_cookies(args.domain, cookie_db_path)
        
        if not cookies:
            print(f"No cookies found for domain: {args.domain}", file=sys.stderr)
            return 1
        
        # Prepare output
        output_file = open(args.output, 'w', newline='', encoding='utf-8') if args.output else sys.stdout
        
        try:
            # Write TSV output
            writer = csv.writer(output_file, delimiter='\t')
            
            # Write header
            writer.writerow(['domain', 'name', 'value'])
            
            # Write cookie data
            for host_key, name, value in cookies:
                writer.writerow([host_key, name, value])
            
            print(f"Found {len(cookies)} cookies for domain: {args.domain}", file=sys.stderr)
            
        finally:
            if args.output:
                output_file.close()
        
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Make sure Chrome is installed and has been run at least once.", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
