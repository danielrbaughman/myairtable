"""generate_meta stamps the generator version into meta.json (myairtable-uzzc).

The version is the one field that lets a checked-in generated tree be matched
against the pinned generator version. It lives in meta.json (one per tree), not
every file's header, to avoid churning thousands of files on a version bump.
"""

from __future__ import annotations

import json
from importlib.metadata import version

from myairtable.meta import generate_meta, generator_version


def test_generator_version_reads_package_metadata():
    # Read from installed metadata, not duplicated/hardcoded.
    assert generator_version() == version("myairtable")


def test_generate_meta_stamps_version_without_disturbing_the_payload(tmp_path):
    payload = {"tables": [{"id": "tblX", "name": "T", "fields": []}]}
    # A minimal stand-in for the real BaseMetadata: the point is that stamping
    # preserves whatever payload it is handed.
    generate_meta(payload, tmp_path)  # ty: ignore[invalid-argument-type]

    written = json.loads((tmp_path / "meta.json").read_text())
    assert written["generator_version"] == generator_version()
    # The original metadata is preserved untouched alongside the stamp.
    assert written["tables"] == payload["tables"]
    # Stamp is first, so a version bump is a one-line diff at the top of the file.
    assert next(iter(written)) == "generator_version"
