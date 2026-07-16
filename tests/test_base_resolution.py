"""Base/credential resolution: aliases, defaults, env — and no global mutation.

Replaces the AirtableCredentials singleton. The point of the registry is that a
raw base id is not discoverable by an agent calling these tools through an MCP
server, so a host registers its bases up front and hands out names.
"""

import pytest

from myairtable import meta


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    """Every test starts with no aliases, no defaults, no env."""
    meta.reset_configuration()
    monkeypatch.delenv("AIRTABLE_BASE_ID", raising=False)
    monkeypatch.delenv("AIRTABLE_API_KEY", raising=False)
    yield
    meta.reset_configuration()


def test_env_is_the_last_resort(monkeypatch):
    monkeypatch.setenv("AIRTABLE_BASE_ID", "appENV")
    monkeypatch.setenv("AIRTABLE_API_KEY", "keyENV")
    assert meta.resolve_base() == ("appENV", "keyENV")


def test_configured_default_beats_env(monkeypatch):
    monkeypatch.setenv("AIRTABLE_BASE_ID", "appENV")
    monkeypatch.setenv("AIRTABLE_API_KEY", "keyENV")
    meta.configure_default(base_id="appDEFAULT", api_key="keyDEFAULT")
    assert meta.resolve_base() == ("appDEFAULT", "keyDEFAULT")


def test_explicit_base_beats_default(monkeypatch):
    monkeypatch.setenv("AIRTABLE_API_KEY", "keyENV")
    meta.configure_default(base_id="appDEFAULT")
    assert meta.resolve_base("appEXPLICIT")[0] == "appEXPLICIT"


def test_alias_carries_its_own_key(monkeypatch):
    """The whole point: one process, several bases, each with its own credential."""
    monkeypatch.setenv("AIRTABLE_BASE_ID", "appENV")
    monkeypatch.setenv("AIRTABLE_API_KEY", "keyENV")
    meta.configure_bases({"crm": ("appCRM", "keyCRM"), "equipment": ("appEQ", "keyEQ")})

    assert meta.resolve_base("crm") == ("appCRM", "keyCRM")
    assert meta.resolve_base("equipment") == ("appEQ", "keyEQ")
    assert meta.resolve_base() == ("appENV", "keyENV")  # unnamed still falls through


def test_unknown_name_is_treated_as_a_raw_id(monkeypatch):
    monkeypatch.setenv("AIRTABLE_API_KEY", "keyENV")
    meta.configure_bases({"crm": ("appCRM", "keyCRM")})
    assert meta.resolve_base("appNOTANALIAS")[0] == "appNOTANALIAS"


def test_configure_default_ignores_unset_flags(monkeypatch):
    """An omitted CLI flag arrives as None and must not clobber the env fallback."""
    monkeypatch.setenv("AIRTABLE_BASE_ID", "appENV")
    monkeypatch.setenv("AIRTABLE_API_KEY", "keyENV")
    meta.configure_default(base_id=None, api_key=None)
    assert meta.resolve_base() == ("appENV", "keyENV")


def test_missing_base_id_raises():
    with pytest.raises(Exception, match="AIRTABLE_BASE_ID not found"):
        meta.resolve_base()


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setenv("AIRTABLE_BASE_ID", "appENV")
    with pytest.raises(Exception, match="AIRTABLE_API_KEY not found"):
        meta.resolve_base()


def test_empty_env_var_still_raises(monkeypatch):
    """AIRTABLE_BASE_ID="" must not resolve to a falsy base id."""
    monkeypatch.setenv("AIRTABLE_BASE_ID", "")
    monkeypatch.setenv("AIRTABLE_API_KEY", "keyENV")
    with pytest.raises(Exception, match="AIRTABLE_BASE_ID not found"):
        meta.resolve_base()


def test_resolution_never_mutates_the_environment(monkeypatch):
    """The library configures itself; only the CLI process may own env."""
    import os

    monkeypatch.setenv("AIRTABLE_BASE_ID", "appENV")
    monkeypatch.setenv("AIRTABLE_API_KEY", "keyENV")
    meta.configure_bases({"crm": ("appCRM", "keyCRM")})
    meta.configure_default(base_id="appDEFAULT", api_key="keyDEFAULT")

    before = dict(os.environ)
    meta.resolve_base("crm")
    meta.resolve_base()
    assert dict(os.environ) == before
