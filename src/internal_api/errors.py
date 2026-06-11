"""Error hierarchy for the internal (unofficial) Airtable API.

Every failure mode gets a distinct type so callers (CLI commands, MCP tools)
can return structured, actionable errors instead of stack traces.
"""


class InternalApiError(Exception):
    """Base for all internal-API failures.

    Public-API features (codegen, docs, the 24 public MCP tools) are never
    affected by these errors.
    """


class NotAuthenticatedError(InternalApiError):
    """No valid session and auto-login could not run (e.g. missing credentials)."""

    def __init__(self, detail: str):
        super().__init__(
            f"Internal-API session unavailable: {detail} "
            "Set AIRTABLE_EMAIL and AIRTABLE_PASSWORD in .env for automatic login, "
            "or run `myairtable login` to authenticate interactively. "
            "Public-API tools are unaffected."
        )


class LoginFailedError(InternalApiError):
    """Automatic login ran but did not produce a valid session."""

    def __init__(self, detail: str):
        super().__init__(
            f"Automatic Airtable login failed: {detail} "
            "Run `myairtable login --headful` to watch the login flow and diagnose. "
            "Public-API tools are unaffected."
        )


class EndpointShapeChangedError(InternalApiError):
    """A v0.3 response did not match the shape we expect.

    The internal API has no published contract — this almost always means
    Airtable changed the endpoint. See docs/airtable-internal-api.md.
    """

    def __init__(self, endpoint: str, detail: str):
        super().__init__(
            f"Unexpected response from internal API endpoint {endpoint}: {detail} "
            "Airtable has likely changed this (unofficial) endpoint. "
            "Public-API tools are unaffected."
        )


class RequestRejectedError(InternalApiError):
    """The server answered with an error status (4xx/5xx) we could not recover from."""

    def __init__(self, endpoint: str, status: int, body_snippet: str):
        super().__init__(f"Internal API endpoint {endpoint} returned HTTP {status}: {body_snippet}")
        self.status = status
