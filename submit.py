#!/usr/bin/env python3

import argparse
import subprocess
import sys
import requests

# Constants - modify these as needed
BASE_URL = "https://example.com/api"
EXTERNAL_PROGRAM = "path/to/external"
ARG1 = "argument1"
ARG2 = "argument2"


def main():
    parser = argparse.ArgumentParser(description="Submit data to API endpoint")
    parser.add_argument("id_string", help="ID string to append to base URL")
    
    args = parser.parse_args()
    id_string = args.id_string
    url = f"{BASE_URL}/{id_string}"
    
    # Run external program and collect output
    try:
        result = subprocess.run([EXTERNAL_PROGRAM, ARG1, ARG2], 
                              capture_output=True, 
                              text=True, 
                              check=True)
        data = result.stdout
    except subprocess.CalledProcessError as e:
        print(f"External program failed with exit code {e.returncode}", file=sys.stderr)
        print(f"Error output: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"External program not found: {EXTERNAL_PROGRAM}", file=sys.stderr)
        sys.exit(1)
    
    # POST data to URL
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        print(f"Successfully posted to {url}")
        print(f"Response status: {response.status_code}")
    except requests.RequestException as e:
        print(f"Failed to POST to {url}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()