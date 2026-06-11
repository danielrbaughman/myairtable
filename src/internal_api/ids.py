"""Airtable ID generation and validation for the internal API."""

import re
import secrets
import string

_BASE62 = string.ascii_letters + string.digits

# All Airtable IDs: 3-letter lowercase prefix + base62 body (e.g. tblXij9xpNwUCLRIM).
_AIRTABLE_ID_RE = re.compile(r"^[a-z]{3}[A-Za-z0-9]+$")


def generate_id(prefix: str, length: int = 14) -> str:
    """Client-generated request-scoped ID (req..., pgl..., flt..., ...)."""
    body = "".join(secrets.choice(_BASE62) for _ in range(length))
    return f"{prefix}{body}"


def generate_request_id() -> str:
    return generate_id("req")


def generate_page_load_id() -> str:
    return generate_id("pgl", 13)


def validate_airtable_id(value: str) -> str:
    """Validate an Airtable ID before it is interpolated into a URL path.

    Guards against path traversal — never build a v0.3 URL from an unvalidated ID.
    """
    if not _AIRTABLE_ID_RE.match(value):
        raise ValueError(f"Not a valid Airtable ID: {value!r}")
    return value
