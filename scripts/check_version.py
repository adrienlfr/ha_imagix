#!/usr/bin/env python3
"""Check that a release tag matches the Home Assistant manifest version."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "imagix" / "manifest.json"
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def normalize_tag(tag: str) -> str:
    """Return the version portion of a release tag."""
    return tag[1:] if tag.startswith("v") else tag


def main() -> int:
    """Validate the supplied tag and manifest version."""
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", help="Release tag, for example v0.5.0")
    args = parser.parse_args()

    tag_version = normalize_tag(args.tag)
    if not SEMVER_PATTERN.fullmatch(tag_version):
        print(f"Invalid semantic version: {args.tag}", file=sys.stderr)
        return 1

    with MANIFEST_PATH.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    manifest_version = manifest.get("version")
    if manifest_version != tag_version:
        print(
            "Version mismatch: "
            f"tag={tag_version}, manifest={manifest_version!r}",
            file=sys.stderr,
        )
        return 1

    print(f"Version {tag_version} is valid and matches manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

