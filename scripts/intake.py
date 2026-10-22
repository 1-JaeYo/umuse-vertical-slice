#!/usr/bin/env python3
"""Give an artist's audio a code name, file it in the private vault, and analyse it.

    python scripts/intake.py "/path/to/Song.mp3" --artist "Real Name" --title "Real Title"

- Assigns the next code (p01, p02, ...). The same audio file added again gets its
  existing code back; it is recognised by fingerprint, not by name.
- Copies the audio into the vault as audio/<code>.<ext>. The original is left where
  it was; delete it yourself if it should not stay there.
- Records code -> artist, title and original filename in the vault's
  participants.json. Nothing in the project folder holds that link.
- Runs scripts/analyse.py on the vault copy and writes raw/<code>.raw.json.

The vault is ~/uMuse-private unless $UMUSE_VAULT says otherwise (see vault.py).
"""
import argparse
import datetime
import hashlib
import json
import shutil
import sys
from pathlib import Path

import vault
from analyse import CHORD_DETECTORS, DEFAULT_DETECTOR, analyse

PROJECT = Path(__file__).resolve().parent.parent


def fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def next_code(participants):
    numbers = [int(c[1:]) for c in participants if vault.CODE.match(c)]
    return f"p{max(numbers, default=0) + 1:02d}"


def file_in_vault(source, artist, title, original_filename=None):
    """Copy audio into the vault under a code. Returns (code, vault audio path, already_there).

    The same audio added again (same fingerprint) gets its existing code back and the
    vault entry is left as it was. `original_filename` is recorded instead of the
    source's own name when the source is a temporary copy, as with a web upload.
    """
    home = vault.location()
    if PROJECT in home.resolve().parents or home.resolve() == PROJECT:
        raise ValueError(f"the vault ({home}) must be outside the project folder")
    (home / "audio").mkdir(parents=True, exist_ok=True)
    home.chmod(0o700)
    (home / "audio").chmod(0o700)

    participants = vault.load(home)
    digest = fingerprint(source)
    code = next((c for c, p in participants.items() if p["sha256"] == digest), None)
    if code:
        return code, home / participants[code]["audio"], True
    name = original_filename or source.name
    code = next_code(participants)
    stored = home / "audio" / f"{code}{Path(name).suffix.lower()}"
    shutil.copy2(source, stored)
    stored.chmod(0o600)
    participants[code] = {
        "artist": artist,
        "title": title,
        "original_filename": name,
        "sha256": digest,
        "added_on": datetime.date.today().isoformat(),
        "audio": str(stored.relative_to(home)),
    }
    vault.save(home, participants)
    return code, stored, False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio")
    parser.add_argument("--artist", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--chords", choices=sorted(CHORD_DETECTORS), default=DEFAULT_DETECTOR)
    parser.add_argument("--notes", help="anything unusual about this run; must not identify the artist")
    args = parser.parse_args()

    source = Path(args.audio).expanduser()
    if not source.is_file():
        print(f"no such file: {source}", file=sys.stderr)
        return 1
    try:
        code, audio, existing = file_in_vault(source, args.artist, args.title)
    except ValueError as e:
        print(f"refusing: {e}", file=sys.stderr)
        return 1
    print(f"{source.name} is already in the vault as {code}" if existing else f"{source.name} -> {code}")

    raw = analyse(audio, code, args.chords, args.notes)
    out = PROJECT / "raw" / f"{code}.raw.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(raw) + "\n")
    print(f"wrote {out.relative_to(PROJECT)}")
    print("next:")
    print(f"  python scripts/convert.py raw/{code}.raw.json data/{code}.json --show-chords")
    print(f"  python scripts/structure.py raw/{code}.raw.json data/{code}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
