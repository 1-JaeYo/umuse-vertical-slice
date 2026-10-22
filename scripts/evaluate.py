#!/usr/bin/env python3
"""Score the analysis against a human transcription of the same track.

    python scripts/evaluate.py --template p01 > reference/p01.truth.json   # then fill it in by ear
    python scripts/evaluate.py reference/p01.truth.json                       # score everything we have
    python scripts/evaluate.py reference/p01.truth.json --sweep               # also try other part settings

The transcription (reference/<code>.truth.json, git-ignored) is written by a person
listening to the track: the researcher, the artist or a musician. Any field may be left
out; only what is there is scored. Chord labels use letter names (Em7, C/G) because that
is what a listener writes; they are turned into scale degrees here and never reach data/.

    {
      "code": "p01",
      "transcribed_by": "who listened",
      "key": "G", "mode": "major",
      "part_starts_seconds": [0, 17.1, 34.3, 51.4],
      "parts_cover_seconds": [0, 60],
      "chords": [{"at_seconds": 0.0, "label": "Em"}, {"at_seconds": 2.1, "label": "D"}],
      "chords_cover_seconds": [0, 60]
    }

What it reports:
- Parts: a boundary counts as found when the analysis has one within BOUNDARY_TOLERANCE_BARS
  bars (at the track's tempo). Precision, recall and F1, as in MIREX structure evaluation.
- Chords: the share of time, every 0.1 s over the transcribed stretch, where the root and
  major/minor agree, for every chord reading we have (the app's results/<code>.json and the
  static reference data/<code>.json).
- Key: whether the transcribed key is the primary reading, another listed reading, or absent.
- --sweep: reruns structure.py with other minimum part lengths and scores each, so the
  setting can be chosen on evidence. It never writes any file.

The Billboard chord window (16 moves) is a choice of what to compare, not a claim about
the track, so a transcription can't check it; it is not scored here.
"""
import argparse
import copy
import json
import re
import sys
from pathlib import Path

from convert import RawError, convert, parse_key, read_label

ROOT = Path(__file__).resolve().parent.parent
BOUNDARY_TOLERANCE_BARS = 1.0
TEMPLATE = {
    "code": "<code>",
    "transcribed_by": "<who listened, e.g. researcher, artist>",
    "key": "<tonic letter, e.g. G>",
    "mode": "<major | minor>",
    "part_starts_seconds": ["<seconds where each part starts, by ear; 0 first>"],
    "parts_cover_seconds": ["<start>", "<end of the stretch you marked parts for; omit if the whole song>"],
    "chords": [{"at_seconds": "<seconds>", "label": "<chord as written, e.g. Em7 or C/G>"}],
    "chords_cover_seconds": ["<start>", "<end>"],
}


def placeholders(node):
    if isinstance(node, dict):
        return any(placeholders(v) for v in node.values())
    if isinstance(node, list):
        return any(placeholders(v) for v in node)
    return isinstance(node, str) and bool(re.match(r"^<.*>$", node))


def boundary_scores(found, truth, tolerance):
    """Precision, recall, F1 of interior boundaries; each true boundary can be matched once."""
    found, truth = sorted(found), sorted(truth)
    used, hits = set(), 0
    for t in truth:
        best = min((abs(f - t), i) for i, f in enumerate(found) if i not in used) if len(used) < len(found) else None
        if best and best[0] <= tolerance:
            used.add(best[1])
            hits += 1
    p = hits / len(found) if found else 0.0
    r = hits / len(truth) if truth else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0), hits


def triad_at(changes, t, end):
    """(degree root triad) sounding at t, from [{at_seconds, degree}]; None for N or nothing."""
    current = None
    for c in changes:
        if c["at_seconds"] > t:
            break
        current = c["degree"]
    return None if current in (None, "N") else current


def score_parts(sections, truth, bpm):
    """Only boundaries inside parts_cover_seconds count, so a partial transcription is scored fairly."""
    tol = BOUNDARY_TOLERANCE_BARS * 4 * 60 / bpm
    lo, hi = truth.get("parts_cover_seconds", [0, float("inf")])
    found = [s["start_seconds"] for s in sections[1:] if lo < s["start_seconds"] < hi - tol]
    true = [t for t in truth["part_starts_seconds"] if lo < t < hi]
    return boundary_scores(found, true, tol), tol


def score_chords(harmony, truth_changes, lo, hi):
    end = harmony["chord_source"]["covers_seconds"][1]
    lo, hi = max(lo, harmony["chord_source"]["covers_seconds"][0]), min(hi, end)
    times = [lo + i / 10 for i in range(int((hi - lo) * 10))]
    pairs = [(triad_at(truth_changes, t, hi), triad_at(harmony["chord_changes"], t, end)) for t in times]
    pairs = [(a, b) for a, b in pairs if a is not None]
    return (sum(a == b for a, b in pairs) / len(pairs) if pairs else None), (lo, hi)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("truth", nargs="?")
    ap.add_argument("--template", metavar="CODE")
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()
    if args.template:
        print(json.dumps(dict(TEMPLATE, code=args.template), indent=2))
        return 0
    if not args.truth:
        print(__doc__)
        return 1
    truth = json.loads(Path(args.truth).read_text())
    if placeholders(truth):
        print(f"{args.truth} still has <placeholders>; fill them in by ear or delete those fields", file=sys.stderr)
        return 1
    code = truth["code"]
    readings = {name: ROOT / folder / f"{code}.json" for name, folder in
                [("app (results/)", "results"), ("static reference (data/)", "data")]}
    readings = {k: json.loads(p.read_text()) for k, p in readings.items() if p.exists()}
    if not readings:
        print(f"no results/{code}.json or data/{code}.json to score", file=sys.stderr)
        return 1

    for name, data in readings.items():
        h, music = data["music"]["harmony"], data["music"]
        print(f"\n== {name}: chords from {h['chord_source']['tool']}")
        if "key" in truth:
            got = [(r["key"], r["mode"], r["relation"]) for r in h["key_reading"]["readings"]]
            match = next((rel for k, m, rel in got if k == truth["key"] and m == truth["mode"]), None)
            print(f"key: transcribed {truth['key']} {truth['mode']} -> "
                  + (f"listed as the {match} reading" if match else "not among the readings"))
        if "part_starts_seconds" in truth and music["structure"].get("available"):
            (p, r, f, hits), tol = score_parts(music["structure"]["sections"], truth, music["groove"]["bpm"])
            print(f"parts: {hits} of {round(hits / r) if r else 0} part starts found "
                  f"within {tol:.1f} s; precision {p:.2f} recall {r:.2f} F1 {f:.2f}")
        if truth.get("chords"):
            tonic, mode = parse_key(h["key"], "key"), h["mode"]
            try:
                tc = [{"at_seconds": c["at_seconds"],
                       "degree": "N" if c["label"] == "N" else read_label(c["label"], tonic, mode, f"truth chords[{i}]")["degree"]}
                      for i, c in enumerate(truth["chords"])]
            except RawError as e:
                print(f"chords: {e}", file=sys.stderr)
                return 1
            lo, hi = truth.get("chords_cover_seconds", [tc[0]["at_seconds"], data["track"]["duration_seconds"]])
            share, (a, b) = score_chords(h, tc, lo, hi)
            print("chords: " + (f"root and major/minor agree {share:.0%} of the time, {a:.0f}-{b:.0f} s"
                                if share is not None else "no overlap with the transcribed stretch"))

    if args.sweep and "part_starts_seconds" in truth:
        import structure as st
        raw = json.loads((ROOT / "raw" / f"{code}.raw.json").read_text())
        base, _, _ = convert(raw)
        print("\n== sweep: minimum part length (structure.py MIN_PART_BEATS)")
        for beats in (8, 12, 16, 20, 24, 32):
            st.MIN_PART_BEATS = beats
            d = st.structure(raw, copy.deepcopy(base))
            (p, r, f, hits), tol = score_parts(d["music"]["structure"]["sections"], truth, raw["bpm"])
            print(f"  {beats:2d} beats: {len(d['music']['structure']['sections']):2d} parts, F1 {f:.2f} "
                  f"(precision {p:.2f}, recall {r:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
