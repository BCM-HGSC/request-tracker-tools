#!/usr/bin/env python3
"""
Chrome Cookie Extractor with Decryption Support
Extracts and decrypts cookies for a specified domain from Chrome's cookie database
and outputs them in TSV format (domain, name, value).
"""

import sqlite3
import os
import sys
import argparse
import platform
import json
import base64
from pathlib import Path
import csv
import traceback

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


def get_chrome_paths():
    """Get the paths to Chrome's cookie database and local state file."""
    system = platform.system()
    
    if system == "Windows":
        base_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
        default_path = os.path.join(base_path, "Default")
    elif system == "Darwin":  # macOS
        base_path = os.path.expanduser("~/Library/Application Support/Google/Chrome")
        default_path = os.path.join(base_path, "Default")
    elif system == "Linux":
        base_path = os.path.expanduser("~/.config/google-chrome")
        default_path = os.path.join(base_path, "Default")
    else:
        raise OSError(f"Unsupported operating system: {system}")
    
    cookie_path = os.path.join(default_path, "Cookies")
    local_state_path = os.path.join(base_path, "Local State")
    
    return cookie_path, local_state_path


def get_encryption_key(local_state_path):
    """Extract the encryption key from Chrome's Local State file."""
    if not CRYPTO_AVAILABLE:
        return None
        
    try:
        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)
        
        # Try different possible locations for the encryption key
        encrypted_key = None
        
        # Standard location
        if 'os_crypt' in local_state and 'encrypted_key' in local_state['os_crypt']:
            encrypted_key = local_state['os_crypt']['encrypted_key']
            print("Found encryption key in os_crypt.encrypted_key", file=sys.stderr)
        
        # Alternative location (some Chrome versions)
        elif 'encryption_key' in local_state:
            encrypted_key = local_state['encryption_key']
            print("Found encryption key in encryption_key", file=sys.stderr)
        
        # Check profile-specific encryption
        elif 'profile' in local_state and 'encryption_key' in local_state['profile']:
            encrypted_key = local_state['profile']['encryption_key']
            print("Found encryption key in profile.encryption_key", file=sys.stderr)
        
        if not encrypted_key:
            print("Warning: No encryption key found in Local State. Trying fallback methods.", file=sys.stderr)
            # Try platform-specific fallback methods
            if platform.system() == "Linux":
                print("Trying Linux fallback encryption key", file=sys.stderr)
                password = b'peanuts'
                salt = b'saltysalt'
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA1(),
                    length=16,
                    salt=salt,
                    iterations=1,
                    backend=default_backend()
                )
                key = kdf.derive(password)
                print(f"Generated fallback key: {key.hex()}", file=sys.stderr)
                return key
            elif platform.system() == "Darwin":
                print("Trying macOS fallback encryption key", file=sys.stderr)
                # For macOS, try the standard method first
                password = b'peanuts'
                salt = b'saltysalt'
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA1(),
                    length=16,
                    salt=salt,
                    iterations=1,
                    backend=default_backend()
                )
                key = kdf.derive(password)
                print(f"Generated fallback key: {key.hex()}", file=sys.stderr)
                return key
            return None
        
        encrypted_key = base64.b64decode(encrypted_key)
        
        # Check for DPAPI prefix
        if encrypted_key.startswith(b'DPAPI'):
            encrypted_key = encrypted_key[5:]  # Remove 'DPAPI' prefix
        
        if platform.system() == "Windows":
            try:
                import win32crypt
                key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
            except ImportError:
                print("Error: win32crypt not available. Install with: pip install pywin32", file=sys.stderr)
                return None
        elif platform.system() == "Darwin":
            # macOS keychain access - try multiple possible entries
            import subprocess
            keychain_entries = [
                ('Chrome Safe Storage', 'Chrome'),
                ('Chromium Safe Storage', 'Chromium'),
                ('Chrome', 'Chrome'),
                ('Safe Storage', 'Chrome')
            ]
            
            for service, account in keychain_entries:
                try:
                    print(f"Trying keychain entry: service='{service}', account='{account}'", file=sys.stderr)
                    result = subprocess.check_output([
                        'security', 'find-generic-password',
                        '-w', '-s', service, '-a', account
                    ], stderr=subprocess.DEVNULL).decode().strip()
                    key = result.encode()
                    print(f"Found keychain entry: {service}/{account}", file=sys.stderr)
                    return key
                except subprocess.CalledProcessError:
                    continue
            
            print("Warning: Could not find Chrome keychain entry. Trying fallback method.", file=sys.stderr)
            # Fallback to the Linux method for macOS
            password = b'peanuts'
            salt = b'saltysalt'
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA1(),
                length=16,
                salt=salt,
                iterations=1,
                backend=default_backend()
            )
            key = kdf.derive(password)
            return key
        else:
            # Linux - try default password
            password = b'peanuts'
            salt = b'saltysalt'
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA1(),
                length=16,
                salt=salt,
                iterations=1,
                backend=default_backend()
            )
            key = kdf.derive(password)
        
        return key
    except KeyError as e:
        print(f"Could not find expected key in Local State: {e}", file=sys.stderr)
        print("This might be an older Chrome version or different profile structure.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Could not get encryption key: {e}", file=sys.stderr)
        return None


def decrypt_cookie_value(encrypted_value, key, debug=False):
    """Decrypt Chrome's encrypted cookie value."""
    if not CRYPTO_AVAILABLE or not key:
        return "<encrypted>"
    
    try:
        if encrypted_value.startswith(b'v10') or encrypted_value.startswith(b'v11'):
            # Remove version prefix
            encrypted_value = encrypted_value[3:]
            # Extract nonce and ciphertext
            nonce = encrypted_value[:12]
            ciphertext = encrypted_value[12:]
            
            if debug:
                print(f"    Decryption attempt: nonce_len={len(nonce)}, ciphertext_len={len(ciphertext)}, key_len={len(key)}", file=sys.stderr)
                print(f"    Nonce: {nonce.hex()}", file=sys.stderr)
            
            # Decrypt using AES-GCM
            cipher = Cipher(
                algorithms.AES(key),
                modes.GCM(nonce),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # Split ciphertext and tag (last 16 bytes are the tag)
            if len(ciphertext) < 16:
                return "<invalid_ciphertext_length>"
            
            data = ciphertext[:-16]
            tag = ciphertext[-16:]
            
            if debug:
                print(f"    Data length: {len(data)}, Tag length: {len(tag)}", file=sys.stderr)
                print(f"    Tag: {tag.hex()}", file=sys.stderr)
            
            plaintext = decryptor.update(data)
            decryptor.finalize_with_tag(tag)
            
            result = plaintext.decode('utf-8')
            if debug:
                print(f"    Successfully decrypted: {result[:50]}{'...' if len(result) > 50 else ''}", file=sys.stderr)
            return result
            
        elif encrypted_value.startswith(b'v20'):
            return "<v20_encryption_not_supported>"
        else:
            return "<unsupported_encryption_format>"
    except Exception as e:
        if debug:
            print(f"    Decryption exception: {type(e).__name__}: {str(e)}", file=sys.stderr)
            print(f"    Full traceback:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        return f"<decrypt_error: {type(e).__name__}: {str(e)}>"


def extract_cookies(domain, cookie_db_path, encryption_key=None, debug=False):
    """Extract cookies for the specified domain from Chrome's cookie database."""
    try:
        # Make a copy of the database to avoid locking issues
        import shutil
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            shutil.copy2(cookie_db_path, tmp_file.name)
            temp_db_path = tmp_file.name
        
        try:
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            
            # First, let's see what columns are available
            if debug:
                cursor.execute("PRAGMA table_info(cookies)")
                columns = [row[1] for row in cursor.fetchall()]
                print(f"Available columns in cookies table: {columns}", file=sys.stderr)
            
            # Build query based on available columns
            query = """
            SELECT host_key, name, value, encrypted_value 
            FROM cookies 
            WHERE host_key LIKE ?
            ORDER BY host_key, name
            """
            
            domain_pattern = f"%{domain}%"
            cursor.execute(query, (domain_pattern,))
            cookies = cursor.fetchall()
            
            conn.close()
            
            # Process cookies and decrypt if necessary
            processed_cookies = []
            for host_key, name, value, encrypted_value in cookies:
                if debug:
                    print(f"Cookie {name}: value='{value}', encrypted_value length={len(encrypted_value) if encrypted_value else 0}", file=sys.stderr)
                    if encrypted_value and len(encrypted_value) > 0:
                        print(f"  Encrypted value starts with: {encrypted_value[:20] if len(encrypted_value) > 20 else encrypted_value}", file=sys.stderr)
                        
                        # Try to provide more detail about the encryption
                        if encrypted_value.startswith(b'v10'):
                            nonce_len = 12
                            tag_len = 16
                            after_prefix = encrypted_value[3:]
                            print(f"  v10 format: nonce={after_prefix[:nonce_len].hex()}, data_len={len(after_prefix)-nonce_len-tag_len}", file=sys.stderr)
                
                if value:
                    # Plain text value available
                    final_value = value
                elif encrypted_value:
                    # Need to decrypt
                    if debug and encryption_key:
                        print(f"  Using key: {encryption_key.hex()[:32]}...", file=sys.stderr)
                    final_value = decrypt_cookie_value(encrypted_value, encryption_key, debug)
                else:
                    final_value = "<empty>"
                
                processed_cookies.append((host_key, name, final_value))
            
            return processed_cookies
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_db_path)
            except:
                pass
        
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
    parser.add_argument(
        "--no-decrypt",
        action="store_true",
        help="Don't attempt to decrypt cookie values"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show debug information including raw encrypted values"
    )
    
    args = parser.parse_args()
    
    if not CRYPTO_AVAILABLE and not args.no_decrypt:
        print("Warning: cryptography library not available. Install with:", file=sys.stderr)
        print("pip install cryptography", file=sys.stderr)
        if platform.system() == "Windows":
            print("pip install pywin32", file=sys.stderr)
        print("Cookie values will show as <encrypted> if they are encrypted.", file=sys.stderr)
        print()
    
    try:
        # Get Chrome paths
        cookie_db_path, local_state_path = get_chrome_paths()
        
        if not os.path.exists(cookie_db_path):
            raise FileNotFoundError(f"Chrome cookie database not found at: {cookie_db_path}")
        
        # Get encryption key if decryption is enabled
        encryption_key = None
        if not args.no_decrypt:
            if os.path.exists(local_state_path):
                encryption_key = get_encryption_key(local_state_path)
                if not encryption_key and platform.system() == "Darwin":
                    # On macOS, also try direct keychain access as a last resort
                    print("Trying direct keychain access...", file=sys.stderr)
                    import subprocess
                    try:
                        # Try the exact command that should work
                        result = subprocess.run([
                            'security', 'find-generic-password', 
                            '-w', '-s', 'Chrome Safe Storage', '-a', 'Chrome'
                        ], capture_output=True, text=True, check=True)
                        if result.stdout.strip():
                            raw_key = result.stdout.strip()
                            # The keychain returns a hex string, convert to bytes
                            if len(raw_key) == 48:  # 24 bytes in hex
                                encryption_key = bytes.fromhex(raw_key)
                                print("Found keychain key (24 bytes)", file=sys.stderr)
                            elif len(raw_key) == 32:  # 16 bytes in hex  
                                encryption_key = bytes.fromhex(raw_key)
                                print("Found keychain key (16 bytes)", file=sys.stderr)
                            else:
                                print(f"Unexpected key length from keychain: {len(raw_key)} chars", file=sys.stderr)
                    except subprocess.CalledProcessError as e:
                        print(f"Keychain access failed: {e}", file=sys.stderr)
            else:
                print("Warning: Chrome Local State file not found. Cannot decrypt cookies.", file=sys.stderr)
        
        # Extract cookies for the domain
        cookies = extract_cookies(args.domain, cookie_db_path, encryption_key, args.debug)
        
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
