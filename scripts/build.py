#!/usr/bin/env python3
"""Check one artist's analysis JSON, then inline it into a standalone HTML page.

    python scripts/build.py data/p01.json out/p01.html [--with-names]

Keeps the data and the template separate while editing, and produces a single
file that opens from the filesystem with no server and no network.

The data check in check.py runs on every build and cannot be skipped. If it
finds anything, nothing is written and every offending field path is printed.

The data names the track only by its code. --with-names reads the real artist and
title from the private vault (see vault.py) and puts them on the page as IDENTITY;
without it IDENTITY is null and the page must show the code. A page built with
names identifies the artist: keep it local and do not share it.
"""
import json
import sys
from pathlib import Path

import vault
from check import check

ROOT = Path(__file__).parent.parent
TEMPLATE = ROOT / "template.html"
MARKER = "/* __UMUSE_DATA__ */"
# The results design is shared with the local web app (web/); the static page inlines it.
SHARED = {"/* __READING_CSS__ */": ROOT / "web" / "static" / "reading.css",
          "/* __READING_JS__ */": ROOT / "web" / "static" / "reading.js"}


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--with-names"]
    with_names = len(args) < len(sys.argv) - 1
    if len(args) != 2:
        print(__doc__)
        return 1

    data_path, out_path = Path(args[0]), Path(args[1])
    data = json.loads(data_path.read_text())

    errors = check(data)
    if errors:
        print(f"REFUSING TO BUILD {data_path}: {len(errors)} problem(s)", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    identity = None
    if with_names:
        try:
            identity = vault.identity(data["track"]["code"])
        except KeyError as e:
            print(f"REFUSING TO BUILD: {e}", file=sys.stderr)
            return 1

    template = TEMPLATE.read_text()
    for marker in [MARKER, *SHARED]:
        if marker not in template:
            print(f"template.html must contain the marker {marker}")
            return 1
    for marker, path in SHARED.items():
        template = template.replace(marker, path.read_text())

    payload = json.dumps(data, indent=2).replace("</", "<\\/")
    who = json.dumps(identity).replace("</", "<\\/")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template.replace(MARKER, f"const DATA = {payload};\nconst IDENTITY = {who};"))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
