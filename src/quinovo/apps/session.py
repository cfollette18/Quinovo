"""Local, honest sign-in for a single-user Quinovo instance.

No enterprise IdP. No OAuth. This is a local tool: the first person to visit
``/signin`` sets a passphrase (stored under ``.data/``, which is gitignored),
and every later visit must enter it. A signed session cookie proves the
caller has claimed this instance.

Never store or log LLM API keys here — the LLM key lives in Settings. The
only secrets in ``.data/`` are the local passphrase and an HMAC signing key.

The data directory defaults to ``<repo>/.data`` but can be overridden via
:data:`DATA_DIR` (tests monkeypatch it to a tmp dir). All paths are derived
lazily from :data:`DATA_DIR` so overriding it takes effect immediately.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Any

from quinovo.workspace import ROOT

# Overridable data directory. Tests monkeypatch this to a tmp_path so the
# real project .data/ is never touched.
DATA_DIR: Path = ROOT / ".data"

COOKIE_NAME = "quinovo_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

__all__ = [
    "COOKIE_MAX_AGE",
    "COOKIE_NAME",
    "DATA_DIR",
    "clear_passphrase",
    "has_passphrase",
    "is_signed_in",
    "issue_session_token",
    "set_passphrase",
    "verify_passphrase",
    "verify_session_token",
]


def _passphrase_path() -> Path:
    return DATA_DIR / "passphrase.txt"


def _secret_path() -> Path:
    return DATA_DIR / "session_secret.txt"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_secret() -> bytes:
    """Load (or create) the HMAC signing key for session tokens."""
    _ensure_data_dir()
    path = _secret_path()
    if path.exists():
        return path.read_bytes()
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    return key


def has_passphrase() -> bool:
    """True if a passphrase has already been claimed for this instance."""
    path = _passphrase_path()
    return path.exists() and path.read_text(encoding="utf-8").strip() != ""


def set_passphrase(passphrase: str) -> None:
    """First-visit: claim this instance by storing a passphrase.

    Raises ``FileExistsError`` if a passphrase is already set, so a later
    visitor cannot silently overwrite it.
    """
    if has_passphrase():
        raise FileExistsError("a passphrase is already set for this instance")
    if not passphrase or len(passphrase) < 4:
        raise ValueError("passphrase must be at least 4 characters")
    _ensure_data_dir()
    # Store a salted hash, not the plaintext, so the file is useless if leaked.
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 200_000)
    payload = {"salt": salt.hex(), "digest": digest.hex()}
    _passphrase_path().write_text(json.dumps(payload), encoding="utf-8")


def verify_passphrase(passphrase: str) -> bool:
    """True if ``passphrase`` matches the stored local passphrase."""
    if not has_passphrase():
        return False
    try:
        payload = json.loads(_passphrase_path().read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    salt = bytes.fromhex(payload.get("salt", ""))
    digest = bytes.fromhex(payload.get("digest", ""))
    candidate = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 200_000)
    return hmac.compare_digest(candidate, digest)


def clear_passphrase() -> None:
    """Remove the stored passphrase (used by tests / reset)."""
    path = _passphrase_path()
    if path.exists():
        path.unlink()


def issue_session_token() -> str:
    """Issue a stateless, HMAC-signed session token for the local user."""
    secret = _load_secret()
    body = "quinovo-local"
    mac = hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def verify_session_token(token: str | None) -> bool:
    """True if ``token`` is a valid session token signed by this instance."""
    if not token or "." not in token:
        return False
    body, mac = token.rsplit(".", 1)
    if body != "quinovo-local":
        return False
    secret = _load_secret()
    expected = hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected)


def is_signed_in(request: Any) -> bool:
    """True if the inbound request carries a valid session cookie."""
    cookie = request.cookies.get(COOKIE_NAME)
    return verify_session_token(cookie)
