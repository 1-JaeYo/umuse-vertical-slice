#!/usr/bin/env python3
"""Run the whole local analysis on one vault track, in order, and check the result.

    python scripts/pipeline.py p01

analyse.py -> convert.py -> structure.py -> billboard.py -> harmonix.py -> check.py,
all on this computer. The chords are Essentia's local estimates (chord_source.tool is
"Essentia"); nothing is sent to Moises or any other service.

Writes raw/<code>.raw.json and results/<code>.json. data/<code>.json is left alone:
that is where the hand-run pipeline (and the Moises reading for p01) lives.
"""
import json
import sys
from pathlib import Path

import billboard
import harmonix
import vault
from analyse import analyse
from check import check
from convert import RawError, convert
from structure import structure

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
RESULTS = ROOT / "results"
TOP_MATCHES = 5


class PipelineError(Exception):
    """A step failed; `step` names it in plain words for the person running the app."""

    def __init__(self, step, detail):
        super().__init__(f"{step}: {detail}")
        self.step, self.detail = step, detail


def readable(audio):
    """Raise PipelineError unless the file decodes to some audio. Run before filing it in the vault."""
    import essentia.standard as es
    try:
        samples = es.MonoLoader(filename=str(audio), sampleRate=44100)()
    except Exception as e:
        raise PipelineError("Reading the audio", e) from e
    if len(samples) == 0:
        raise PipelineError("Reading the audio", "the file decoded to no sound")


def run(audio, code):
    """Analyse one track. Returns (data, problems); problems is check()'s list, empty when valid."""
    try:
        raw = analyse(audio, code)
    except Exception as e:
        raise PipelineError("Reading the audio", e) from e
    RAW.mkdir(exist_ok=True)
    (RAW / f"{code}.raw.json").write_text(json.dumps(raw) + "\n")
    try:
        data, _log, _before = convert(raw)
    except RawError as e:
        raise PipelineError("Turning the analysis into chords and key", e) from e
    try:
        data = structure(raw, data)
    except Exception as e:
        raise PipelineError("Finding the parts of the song", e) from e
    try:
        data, _ = billboard.compare(data, TOP_MATCHES)
        if data["music"]["structure"].get("available"):
            data, _ = harmonix.compare(data, TOP_MATCHES)
    except Exception as e:
        raise PipelineError("Comparing with the song collections", e) from e
    problems = check(data)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{code}.json").write_text(json.dumps(data, indent=2) + "\n")
    return data, problems


def main() -> int:
    if len(sys.argv) != 2 or not vault.CODE.match(sys.argv[1]):
        print(__doc__)
        return 1
    code = sys.argv[1]
    home = vault.location()
    audio = home / vault.load(home)[code]["audio"]
    data, problems = run(audio, code)
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    print(f"{code}: {len(problems)} problem(s)" if problems else f"{code}: ok, wrote results/{code}.json")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
