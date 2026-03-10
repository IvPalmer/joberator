"""
LinkedIn persistent authentication.

Reads li_at cookie from your browser (Chrome/Brave) automatically.
You just need to be logged into LinkedIn in your browser.
On first use, macOS will ask you to approve Keychain access.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from hashlib import pbkdf2_hmac

from Crypto.Cipher import AES

JOBERATOR_DIR = os.path.expanduser("~/.joberator")
COOKIES_PATH = os.path.join(JOBERATOR_DIR, "cookies.json")

# Chrome cookie DB locations (macOS)
CHROME_COOKIE_PATHS = [
    ("Chrome Profile 1", "~/Library/Application Support/Google/Chrome/Profile 1/Cookies"),
    ("Chrome Default", "~/Library/Application Support/Google/Chrome/Default/Cookies"),
    ("Chrome Profile 2", "~/Library/Application Support/Google/Chrome/Profile 2/Cookies"),
    ("Chrome Profile 4", "~/Library/Application Support/Google/Chrome/Profile 4/Cookies"),
    ("Brave", "~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies"),
]

LINKEDIN_COOKIE_NAMES = ("li_at", "JSESSIONID", "li_rm", "lang")


def _get_chrome_key(browser="Chrome") -> bytes | None:
    """Get Chrome's encryption key from macOS Keychain.

    This triggers a one-time Keychain access prompt.
    """
    service = "Chrome Safe Storage" if browser == "Chrome" else "Brave Safe Storage"
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s", service,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            password = result.stdout.strip()
            # Derive the key using PBKDF2
            return pbkdf2_hmac("sha1", password.encode(), b"saltysalt", 1003, dklen=16)
    except Exception:
        pass
    return None


def _decrypt_chrome_value(encrypted_value: bytes, key: bytes) -> str:
    """Decrypt a Chrome v10 encrypted cookie value."""
    if not encrypted_value:
        return ""

    # v10 prefix = standard macOS Chrome encryption
    if encrypted_value[:3] == b"v10":
        encrypted_value = encrypted_value[3:]
        # AES-CBC with 16-byte IV of spaces
        iv = b" " * 16
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted_value)
        # Remove PKCS7 padding
        padding_len = decrypted[-1]
        if isinstance(padding_len, int) and 1 <= padding_len <= 16:
            if all(b == padding_len for b in decrypted[-padding_len:]):
                decrypted = decrypted[:-padding_len]
        # First 32 bytes are garbled CBC noise — extract printable portion
        text = decrypted.decode("latin-1")
        # Find the start of the actual printable value
        for i, ch in enumerate(text):
            if ch.isprintable() and ord(ch) < 128 and ch not in "\t\n\r":
                # Check if this starts a run of printable chars
                if all(
                    c.isprintable() and ord(c) < 128
                    for c in text[i : i + min(4, len(text) - i)]
                ):
                    return text[i:]
        return text

    # Unencrypted (rare)
    return encrypted_value.decode("utf-8", errors="replace")


def _extract_cookies_from_db(db_path: str, key: bytes) -> list[dict]:
    """Extract LinkedIn cookies from a Chrome cookies database."""
    db_path = os.path.expanduser(db_path)
    if not os.path.exists(db_path):
        return []

    # Copy DB since Chrome locks it
    tmp = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy2(db_path, tmp)
        conn = sqlite3.connect(tmp)
        cursor = conn.execute(
            """
            SELECT name, encrypted_value, host_key, path, expires_utc, is_secure, is_httponly
            FROM cookies
            WHERE host_key LIKE '%linkedin.com%' AND name IN (?, ?, ?, ?)
            """,
            LINKEDIN_COOKIE_NAMES,
        )
        cookies = []
        for name, enc_val, host, path, expires_utc, is_secure, is_httponly in cursor:
            value = _decrypt_chrome_value(enc_val, key)
            if value:
                # Chrome stores expires as microseconds since 1601-01-01
                # Convert to Unix timestamp
                expires = 0
                if expires_utc:
                    expires = (expires_utc / 1_000_000) - 11644473600
                cookies.append({
                    "name": name,
                    "value": value,
                    "domain": host,
                    "path": path,
                    "expires": expires,
                    "secure": bool(is_secure),
                    "httpOnly": bool(is_httponly),
                })
        conn.close()
        return cookies
    except Exception:
        return []
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def refresh_cookies() -> dict:
    """Extract LinkedIn cookies from installed browsers.

    Tries Chrome profiles first, then Brave.
    Returns dict with success status and message.
    """
    # Try Chrome first, then Brave
    for label, db_path in CHROME_COOKIE_PATHS:
        browser = "Brave" if "Brave" in label else "Chrome"
        key = _get_chrome_key(browser)
        if not key:
            continue

        cookies = _extract_cookies_from_db(db_path, key)
        li_at = next((c for c in cookies if c["name"] == "li_at"), None)

        if li_at and li_at["value"]:
            # Check if expired
            if li_at["expires"] > 0 and li_at["expires"] < time.time():
                continue

            # Save cookies
            os.makedirs(JOBERATOR_DIR, exist_ok=True)
            with open(COOKIES_PATH, "w") as f:
                json.dump(cookies, f, indent=2)

            return {
                "success": True,
                "source": label,
                "message": f"LinkedIn cookies extracted from {label}.",
            }

    return {
        "success": False,
        "error": (
            "Could not find a LinkedIn session cookie (li_at) in any browser.\n"
            "Open LinkedIn in Chrome or Brave and make sure you're logged in,\n"
            "then try again. Use `linkedin_connect` to open LinkedIn automatically."
        ),
    }


def get_li_at_cookie() -> str | None:
    """Read the li_at cookie. Always reads fresh from browser."""
    result = refresh_cookies()
    if result["success"]:
        with open(COOKIES_PATH) as f:
            cookies = json.load(f)
        for c in cookies:
            if c["name"] == "li_at":
                return c["value"]
    return None


def get_jsessionid() -> str | None:
    """Read the JSESSIONID cookie (used as CSRF token for Voyager API).

    Call get_li_at_cookie() first to ensure cookies are fresh.
    """
    if not os.path.exists(COOKIES_PATH):
        return None
    with open(COOKIES_PATH) as f:
        cookies = json.load(f)
    for c in cookies:
        if c["name"] == "JSESSIONID":
            return c["value"].strip('"')
    return None


def is_connected() -> bool:
    """Check if we have a valid LinkedIn session (checks browser if needed)."""
    return get_li_at_cookie() is not None


def open_linkedin_in_browser():
    """Open LinkedIn in the default browser to trigger cookie refresh."""
    try:
        subprocess.run(["open", "https://www.linkedin.com/feed/"], check=True)
        return True
    except Exception:
        return False


def clear_session():
    """Remove saved cookies."""
    if os.path.exists(COOKIES_PATH):
        os.remove(COOKIES_PATH)
