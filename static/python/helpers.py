import os
from typing import Sequence


def get_api_key() -> str:
    return os.getenv("AIRTABLE_API_KEY") or ""


def get_base_id() -> str:
    return os.getenv("AIRTABLE_BASE_ID") or ""


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
