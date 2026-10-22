"""The private vault: the only place a code name is linked to a real artist.

Layout (default ~/uMuse-private, or $UMUSE_VAULT):

    participants.json        code -> artist, title, original filename, fingerprint
    audio/p01.mp3            the audio, renamed to its code

The vault lives outside the project so it is never committed, shared or synced with
the code. Everything else in the pipeline sees only the code.
"""
import json
import os
import re
from pathlib import Path

CODE = re.compile(r"^p\d{2,}$")


def location():
    return Path(os.environ.get("UMUSE_VAULT", Path.home() / "uMuse-private")).expanduser()


def load(vault):
    path = vault / "participants.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save(vault, participants):
    path = vault / "participants.json"
    path.write_text(json.dumps(participants, indent=2, ensure_ascii=False) + "\n")
    path.chmod(0o600)


def identity(code, vault=None):
    """Real artist and title for a code, or an error naming what is missing."""
    vault = vault or location()
    participants = load(vault)
    if code not in participants:
        raise KeyError(f"{code} is not in {vault / 'participants.json'}")
    p = participants[code]
    return {"artist": p["artist"], "title": p["title"]}
