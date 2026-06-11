"""Airtable internal (unofficial) v0.3 API support.

Everything in this package talks to Airtable's PRIVATE web-client API
(`airtable.com/v0.3/...`) — the same one the browser UI uses. There is no
published contract; Airtable can change or remove endpoints at any time.

This package is deliberately separate from the public meta-API code
(`src/meta.py`): it has its own models, its own error hierarchy, and its own
transport. Do not mix the two — anything imported from here is understood to
be reverse-engineered surface that can break without notice.

Endpoint shapes are documented (and spike-verified) in
`docs/airtable-internal-api.md`.
"""

from .errors import EndpointShapeChangedError, InternalApiError, LoginFailedError, NotAuthenticatedError
from .transport import InternalApiTransport

__all__ = [
    "EndpointShapeChangedError",
    "InternalApiError",
    "InternalApiTransport",
    "LoginFailedError",
    "NotAuthenticatedError",
]
