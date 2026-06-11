"""httpx transport for the internal v0.3 API.

Spike-verified design (docs/airtable-internal-api.md, "Spike findings"):

- Plain httpx with the Firefox session cookies, the x- headers below, and a
  matching User-Agent is not blocked by PerimeterX for /v0.3/ reads. The
  browser is only ever needed at login time (auth.py).
- `Accept: application/json` + schema-only params keep responses JSON
  (requesting row data can switch the server to a binary streaming format).
- Sessions live ~1 year; responses rotate load-balancer cookies, so the jar
  is written back to disk after requests.

Read-only by design: the mutation envelope (stringifiedObjectParams POST body,
_csrf, secretSocketId) is deliberately NOT implemented here yet. When a write
feature lands, it becomes an additional method on this transport — reads must
not change.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .auth import load_state, login, save_state
from .errors import EndpointShapeChangedError, NotAuthenticatedError, RequestRejectedError
from .ids import generate_page_load_id, generate_request_id

_BASE_URL = "https://airtable.com"
_RETRYABLE_STATUSES = {429, 503}
_MAX_RETRIES = 3


def _local_timezone() -> str:
    """Best-effort IANA timezone name (the x-time-zone header)."""
    try:
        localtime = Path("/etc/localtime").resolve()
        parts = localtime.parts
        if "zoneinfo" in parts:
            idx = parts.index("zoneinfo")
            return "/".join(parts[idx + 1 :])
    except OSError:
        pass
    return "UTC"


class InternalApiTransport:
    """Authenticated GET access to airtable.com/v0.3/.

    Auto-authenticates: if there is no persisted session (or it has expired),
    runs the scripted headless-Firefox login using AIRTABLE_EMAIL /
    AIRTABLE_PASSWORD. Session state persists at ~/.myairtable/internal-session.json.
    """

    def __init__(self) -> None:
        self._client: httpx.Client | None = None
        self._state: dict[str, Any] | None = None
        self._timezone = _local_timezone()
        # get() is called concurrently by the view-fetching layer; httpx.Client
        # is thread-safe for requests, but session (re)builds and cookie
        # write-back are not — guard them.
        self._session_lock = threading.Lock()
        self._cookie_lock = threading.Lock()

    # -- session ---------------------------------------------------------

    def _ensure_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        with self._session_lock:
            if self._client is not None:  # another thread won the race
                return self._client
            state = load_state()
            if state is None:
                state = login(headless=True)  # raises NotAuthenticatedError / LoginFailedError
            self._state = state
            self._client = self._build_client(state)
            return self._client

    def _build_client(self, state: dict[str, Any]) -> httpx.Client:
        cookies = httpx.Cookies()
        for c in state["cookies"]:
            if "airtable" in c.get("domain", ""):
                cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
        headers = {
            "User-Agent": state.get("userAgent") or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:142.0) Gecko/20100101 Firefox/142.0",
            "Accept": "application/json",
            "x-airtable-inter-service-client": "webClient",
            "x-requested-with": "XMLHttpRequest",
            "x-user-locale": "en",
            "x-time-zone": self._timezone,
        }
        return httpx.Client(base_url=_BASE_URL, cookies=cookies, headers=headers, timeout=60)

    def _relogin(self, stale_client: httpx.Client) -> None:
        """Session went stale server-side: force a fresh scripted login.

        Concurrent threads that hit 401 with the same stale client only
        trigger one login — later arrivals see the already-swapped client.
        """
        with self._session_lock:
            if self._client is not None and self._client is not stale_client:
                return  # another thread already re-logged-in
            if self._client is not None:
                self._client.close()
                self._client = None
            state = login(headless=True)
            self._state = state
            self._client = self._build_client(state)

    def _write_back_cookies(self, client: httpx.Client) -> None:
        """Persist rotated cookies (AWSALBTG*, brw, mbpg, ...) so the jar stays fresh."""
        if self._state is None:
            return
        with self._cookie_lock:
            self._write_back_cookies_locked(client)

    def _write_back_cookies_locked(self, client: httpx.Client) -> None:
        assert self._state is not None
        by_name = {(c["name"], c.get("domain", "")): c for c in self._state["cookies"]}
        for jar_cookie in client.cookies.jar:
            key = (jar_cookie.name, jar_cookie.domain or "")
            if key in by_name:
                by_name[key]["value"] = jar_cookie.value
            else:
                by_name[key] = {
                    "name": jar_cookie.name,
                    "value": jar_cookie.value,
                    "domain": jar_cookie.domain or "",
                    "path": jar_cookie.path or "/",
                    "expires": jar_cookie.expires or -1,
                }
        self._state["cookies"] = list(by_name.values())
        self._state["savedAt"] = time.time()
        save_state(self._state)

    # -- requests --------------------------------------------------------

    def get(
        self,
        path: str,
        object_params: dict[str, Any] | None = None,
        app_id: str | None = None,
    ) -> dict[str, Any]:
        """GET a /v0.3/ endpoint and return the parsed JSON body.

        `object_params` becomes the stringifiedObjectParams query argument.
        Retries once on auth failure (fresh login) and with backoff on 429/503.
        """
        client = self._ensure_client()
        params: dict[str, str] = {"requestId": generate_request_id()}
        if object_params is not None:
            params["stringifiedObjectParams"] = json.dumps(object_params)
        headers = {"x-airtable-page-load-id": generate_page_load_id()}
        if app_id:
            headers["x-airtable-application-id"] = app_id

        relogged_in = False
        backoff = 0.5
        attempts = 0
        while True:
            try:
                response = client.request("GET", path, params=params, headers=headers)
            except httpx.HTTPError as e:
                raise RequestRejectedError(path, 0, f"network error: {e}") from e

            if response.status_code in (401, 403) and not relogged_in:
                relogged_in = True
                self._relogin(client)
                client = self._client
                assert client is not None
                continue
            if response.status_code in _RETRYABLE_STATUSES and attempts < _MAX_RETRIES:
                attempts += 1
                time.sleep(backoff)
                backoff *= 2
                continue
            break

        self._write_back_cookies(client)

        if response.status_code in (401, 403):
            raise NotAuthenticatedError(f"endpoint {path} still returns HTTP {response.status_code} after a fresh login.")
        if response.status_code != 200:
            raise RequestRejectedError(path, response.status_code, response.text[:200])

        text = response.text
        if not text.lstrip().startswith("{"):
            raise EndpointShapeChangedError(path, "response is not a JSON object (binary/streaming format?).")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise EndpointShapeChangedError(path, f"response is not valid JSON: {e}") from e

    def verify_session(self) -> bool:
        """Cheap session probe (getUserProperties)."""
        try:
            self.get("/v0.3/getUserProperties")
            return True
        except NotAuthenticatedError:
            return False

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
