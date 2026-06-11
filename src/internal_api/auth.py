"""Scripted Airtable login via Playwright Firefox.

Spike-verified facts this module is built on (docs/airtable-internal-api.md,
"Spike findings"):

- PerimeterX blocks ALL Chromium automation (vanilla, Patchright, real Chrome,
  even headful) with a "Verify it's you" interstitial. Playwright **Firefox**
  gets the real login form, headless.
- The React login form does not enable its submit button on `fill()` — real
  keystrokes (`press_sequentially`) are required.
- A Transcend cookie-consent overlay (#transcend-shadow-root) intercepts
  pointer events; block its script at the network level and remove the node.
- The password-step submit button can stay disabled — press Enter instead.
- The session cookie (__Host-airtable-session) lives ~1 year, so logins are rare.

Playwright is an optional dependency (`myairtable[internal]`); import errors
surface as NotAuthenticatedError with install instructions.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

from .errors import LoginFailedError, NotAuthenticatedError

STATE_FILE = Path.home() / ".myairtable" / "internal-session.json"

_LOGIN_URL = "https://airtable.com/login"


def load_state() -> dict[str, Any] | None:
    """Load the persisted session state ({cookies, userAgent, savedAt}) if present."""
    if not STATE_FILE.exists():
        return None
    try:
        state = json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict) or "cookies" not in state:
        return None
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))
    STATE_FILE.chmod(0o600)  # session cookies are credentials


def _credentials() -> tuple[str, str]:
    email = os.environ.get("AIRTABLE_EMAIL", "").strip()
    password = os.environ.get("AIRTABLE_PASSWORD", "").strip()
    if not email or not password:
        raise NotAuthenticatedError("AIRTABLE_EMAIL / AIRTABLE_PASSWORD are not set.")
    return email, password


def login(headless: bool = True) -> dict[str, Any]:
    """Run the scripted login flow and persist + return the session state.

    Raises NotAuthenticatedError (missing credentials / missing playwright) or
    LoginFailedError (flow ran but no session came out).
    """
    email, password = _credentials()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise NotAuthenticatedError(
            "playwright is not installed. Install the internal extra: `uv pip install 'myairtable[internal]'` then `playwright install firefox`."
        ) from e

    with sync_playwright() as pw:
        try:
            browser = pw.firefox.launch(headless=headless)
        except Exception as e:  # missing browser binary
            raise NotAuthenticatedError(f"could not launch Firefox ({e}). Run `playwright install firefox`.") from e

        ctx = browser.new_context()
        try:
            # The Transcend consent overlay intercepts pointer events on the
            # login form — keep it from loading at all.
            ctx.route(lambda url: "transcend" in url.lower(), lambda route: route.abort())
            page = ctx.new_page()
            page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2_000)

            title = page.title()
            if "Verify" in title:
                raise LoginFailedError(
                    "Airtable served its bot-detection interstitial ('Verify it's you') "
                    "to the Firefox login page. This worked at spike time (2026-06-10) — "
                    "Airtable may have extended detection to Firefox automation."
                )

            if "/login" in page.url:
                _drive_login_form(page, email, password)

            if "/login" in page.url:
                err = _visible_error_text(page)
                raise LoginFailedError(f"still on the login page after submitting credentials. {err}")

            # Ground-truth probe from inside the page (cookies attach automatically).
            status = page.evaluate(
                """async () => {
                    const res = await fetch('https://airtable.com/v0.3/getUserProperties', {
                        headers: {
                            'x-airtable-inter-service-client': 'webClient',
                            'x-requested-with': 'XMLHttpRequest',
                        },
                    });
                    return res.status;
                }"""
            )
            if status != 200:
                raise LoginFailedError(f"post-login session probe returned HTTP {status}.")

            user_agent = page.evaluate("() => navigator.userAgent")
            storage = ctx.storage_state()
            state = {
                "cookies": storage["cookies"],
                "userAgent": user_agent,
                "savedAt": time.time(),
            }
            save_state(state)
            return state
        finally:
            ctx.close()
            browser.close()


def _drive_login_form(page: Any, email: str, password: str) -> None:
    """Two-step form: email -> Continue -> password -> Enter."""
    page.evaluate("() => document.getElementById('transcend-shadow-root')?.remove()")

    email_input = page.locator('input[type="email"]').first
    email_input.wait_for(state="visible", timeout=10_000)
    email_input.click()
    email_input.press_sequentially(email, delay=30)  # fill() doesn't enable the submit button
    page.locator('button[type="submit"]').first.click()

    pw_input = page.locator('input[type="password"]').first
    pw_input.wait_for(state="visible", timeout=15_000)
    page.evaluate("() => document.getElementById('transcend-shadow-root')?.remove()")  # overlay respawns
    pw_input.click()
    pw_input.press_sequentially(password, delay=30)
    pw_input.press("Enter")  # the submit button can stay disabled — Enter always works

    try:
        page.wait_for_url(lambda u: "/login" not in u, timeout=30_000)
    except Exception:
        pass  # caller inspects page.url and surfaces the on-page error
    page.wait_for_timeout(2_000)


def _visible_error_text(page: Any) -> str:
    try:
        match = page.evaluate("() => document.body.innerText.match(/[^\\n]*(incorrect|invalid|wrong|error|too many)[^\\n]*/i)?.[0] ?? ''")
        return f"Page says: {match!r}" if match else "No visible error message found."
    except Exception:
        return ""
