import os
from typing import Sequence

# Config registry keyed by base_id
_config_registry: dict[str, dict[str, str]] = {}
_default_base_id: str | None = None


def set_airtable_config(base_id: str, api_key: str, endpoint_url: str = "https://api.airtable.com") -> None:
    """Register config for a specific base_id."""
    global _default_base_id
    _config_registry[base_id] = {
        "api_key": api_key,
        "base_id": base_id,
        "endpoint_url": endpoint_url,
    }
    _default_base_id = base_id  # Last registered becomes default


def get_config_for_base(base_id: str) -> dict[str, str] | None:
    """Get config for a specific base_id."""
    return _config_registry.get(base_id)


def get_api_key(base_id: str | None = None) -> str:
    """Get API key, checking registry first, then env var."""
    # If base_id provided, look up in registry
    if base_id:
        config = _config_registry.get(base_id)
        if config and config.get("api_key"):
            return config["api_key"]
    # Fall back to default base_id's config
    if _default_base_id:
        config = _config_registry.get(_default_base_id)
        if config and config.get("api_key"):
            return config["api_key"]
    # Fall back to env var
    return os.getenv("AIRTABLE_API_KEY") or ""


def get_base_id() -> str:
    """Get base ID, checking registry first, then env var."""
    if _default_base_id:
        return _default_base_id
    return os.getenv("AIRTABLE_BASE_ID") or ""


def get_endpoint_url(base_id: str | None = None) -> str:
    """Get endpoint URL, checking registry first, then default."""
    # If base_id provided, look up in registry
    if base_id:
        config = _config_registry.get(base_id)
        if config and config.get("endpoint_url"):
            return config["endpoint_url"]
    # Fall back to default base_id's config
    if _default_base_id:
        config = _config_registry.get(_default_base_id)
        if config and config.get("endpoint_url"):
            return config["endpoint_url"]
    # Fall back to default
    return "https://api.airtable.com"


def validate_key(name: str, valid_names: list[str]):
    if name not in valid_names:
        raise ValueError(f"""Invalid field name:
{name}
""")


def validate_keys(field_names: Sequence[str], valid_names: list[str]):
    invalid_names = []
    for name in field_names:
        if name not in valid_names:
            invalid_names.append(name)
    if invalid_names:
        raise ValueError(f"""Invalid field names:
{"\n".join(invalid_names)}
""")


base_url: str = "https://airtable.com"


def build_url(base_id: str = "", table_id: str = "", view_id: str = "", record_id: str = "") -> str:
    if not base_id:
        return base_id
    elif not table_id:
        return f"{base_url}/{base_id}"
    elif not view_id and not record_id:
        return f"{base_url}/{base_id}/{table_id}"
    elif view_id and not record_id:
        return f"{base_url}/{base_id}/{table_id}/{view_id}"
    elif record_id and not view_id:
        return f"{base_url}/{base_id}/{table_id}/{record_id}"
    else:
        return f"{base_url}/{base_id}/{table_id}/{view_id}/{record_id}"
