#!/usr/bin/env python3
"""Turn raw pipeline output into the harmony, tempo and melody parts of data/<artist>.json.

    python scripts/convert.py raw/kene.raw.json data/kene.json [--show-chords]

This is the only place letter-name chords exist. Everything it writes uses scale
degrees (see the table in CLAUDE.md), so nothing downstream ever sees a letter
name except the tonic of a key.

It writes `track`, `music.harmony`, `music.groove` and `music.melody`. Structure,
comparisons and population context are added by later scripts; until then the
file will not pass build.py, which is intended.

Short, weak chords are merged away before anything else sees them (see
merge_short_chords). The rule, its thresholds and the number merged are written
into `music.harmony.chord_filter`, and every merge is printed.

Raw input (written by scripts/analyse.py; every field required unless marked optional):

    {
      "code": "p01", "duration_seconds": number,
      "analysed_on": "YYYY-MM-DD", "pipeline": str, "notes": str (optional),
      "key": "A", "scale": "major" | "minor", "key_strength": number 0-1,
      "key_profiles": [{"profile": str, "key": str, "scale": str, "strength": number}],
      "bpm": number, "beats_seconds": [number, ...],
      "beat_confidence": number,
      "beat_confidence_scale_max": number,   # top of the beat tracker's own scale; not guessed here
      "chords": [{"at_seconds": number, "chord": "Am" | "C#" | "Bb" | "N", "strength": number}, ...]
    }

`chords` may be one entry per frame or per beat; repeats are collapsed into changes.
Any chord label it cannot parse is an error, not a guess.
"""
import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]  # Essentia's spellings
CHORD = re.compile(r"^([A-G])([#b]?)(m?)$")
NUMERALS = {
    "major": ["I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII"],
    "minor": ["I", "bII", "II", "III", "#III", "IV", "#IV", "V", "VI", "#VI", "VII", "#VII"],
}
LOOP_LENGTH = 4
MIN_CHORD_BEATS = 0.25
MIN_SECTION_ENDINGS = 3  # fewer part endings than this can't show what "most parts" end on
MELODY_REASON = "Melody analysis is scheduled for Sprint 2 and was not run on this track."


class RawError(ValueError):
    pass


def pitch_class(letter, accidental):
    return (PITCH[letter] + {"": 0, "#": 1, "b": -1}[accidental]) % 12


def parse_chord(label, where):
    """'Am' -> (9, 'minor'); 'N' -> None."""
    if label == "N":
        return None
    m = CHORD.match(label)
    if not m:
        raise RawError(f"{where}: cannot read chord label {label!r}")
    letter, acc, minor = m.groups()
    return pitch_class(letter, acc), "minor" if minor else "major"


def parse_key(label, where):
    m = re.match(r"^([A-G])([#b]?)$", str(label))
    if not m:
        raise RawError(f"{where}: cannot read tonic {label!r}")
    return pitch_class(*m.groups())


def to_degree(chord, tonic, mode):
    """Scale degree relative to the key, upper case major, lower case minor."""
    if chord is None:
        return "N"
    root, quality = chord
    numeral = NUMERALS[mode][(root - tonic) % 12]
    if quality == "minor":
        # keep the accidental, lower-case the numeral
        return numeral[0] + numeral[1:].lower() if numeral[0] in "b#" else numeral.lower()
    return numeral


# ---- full chord labels (Chordino, Moises) ---------------------------------------

LABEL = re.compile(r"^([A-G])([#b]?)(m(?!aj))?(.*?)(?:/([A-G])([#b]?))?$")
DETAILS = {"", "7", "maj7", "6", "9", "maj9", "add9", "11", "13", "sus2", "sus4", "7sus4",
           "dim", "dim7", "7b5", "aug"}
MINOR_SHAPED = {"dim", "dim7", "7b5"}  # minor third, so the degree is written lower case


def read_label(label, tonic, mode, where):
    """'Em7' -> {'degree': 'vi', 'detail': '7'}; 'C/G' -> {'degree': 'IV', 'bass_degree': 'I'} (in G major).

    For chord labels that carry more than major/minor (Chordino, Moises). The degree is the
    root triad; what the label adds is kept in `detail`, and a slash-chord bass in `bass_degree`.
    """
    m = LABEL.match(label)
    if not m or m.group(4) not in DETAILS:
        raise RawError(f"{where}: cannot read chord {label!r}; teach convert.read_label this label")
    letter, acc, minor, detail, bass_letter, bass_acc = m.groups()
    quality = "minor" if minor or detail in MINOR_SHAPED else "major"
    out = {"degree": to_degree((pitch_class(letter, acc), quality), tonic, mode)}
    if detail:
        out["detail"] = detail
    if bass_letter:
        out["bass_degree"] = NUMERALS[mode][(pitch_class(bass_letter, bass_acc) - tonic) % 12]
    return out


# ---- chord segments and the short-chord filter --------------------------------

def segments(raw_chords, duration):
    """Runs of the same chord, each with its span and the strengths of its frames."""
    segs = []
    for i, c in enumerate(raw_chords):
        where = f"chords[{i}]"
        if not isinstance(c, dict) or not {"at_seconds", "chord", "strength"} <= c.keys():
            raise RawError(f"{where}: needs at_seconds, chord and strength")
        if segs and c["at_seconds"] <= segs[-1]["frame_times"][-1]:
            raise RawError(f"{where}: timestamps must increase")
        chord = parse_chord(c["chord"], where)
        if segs and segs[-1]["chord"] == chord:
            segs[-1]["strengths"].append(c["strength"])
            segs[-1]["frame_times"].append(c["at_seconds"])
        else:
            segs.append({"start": float(c["at_seconds"]), "chord": chord,
                         "strengths": [c["strength"]], "frame_times": [c["at_seconds"]]})
    for this, nxt in zip(segs, segs[1:]):
        this["end"] = nxt["start"]
    if segs:
        segs[-1]["end"] = float(duration)
    return segs


def strength(seg):
    return statistics.fmean(seg["strengths"])


def merge_short_chords(segs, min_seconds, max_strength):
    """Absorb chords that are both short and weak into the longer neighbour.

    A segment qualifies when it lasts less than `min_seconds` AND its mean chord
    strength is below `max_strength`. A short chord the detector is sure about
    survives. Qualifying segments are taken shortest first (earliest on a tie) and
    absorbed into the longer of their two neighbours (the earlier on a tie). If that
    leaves the same chord on both sides, the two are joined. The absorbed frames'
    strengths are dropped, since they belonged to a different chord.

    Returns the surviving segments and a log of every merge.
    """
    segs = [dict(s, strengths=list(s["strengths"])) for s in segs]
    log = []
    while len(segs) > 1:
        candidates = [i for i, s in enumerate(segs)
                      if s["end"] - s["start"] < min_seconds and strength(s) < max_strength]
        if not candidates:
            break
        i = min(candidates, key=lambda j: (segs[j]["end"] - segs[j]["start"], segs[j]["start"]))
        short = segs[i]
        prev = segs[i - 1] if i > 0 else None
        nxt = segs[i + 1] if i + 1 < len(segs) else None
        if nxt is None or (prev is not None and prev["end"] - prev["start"] >= nxt["end"] - nxt["start"]):
            into = prev
            prev["end"] = short["end"]
        else:
            into = nxt
            nxt["start"] = short["start"]
        log.append({"start": short["start"], "seconds": short["end"] - short["start"],
                    "chord": short["chord"], "strength": strength(short), "into": into["chord"]})
        del segs[i]
        if prev is not None and nxt is not None and prev["chord"] == nxt["chord"]:
            prev["end"] = nxt["end"]
            prev["strengths"] += nxt["strengths"]
            segs.remove(nxt)
    return segs, log


def labelled_changes(raw_chords, tonic, mode):
    """Chord changes from full labels (Chordino): degree, plus detail and bass when the label has them."""
    changes = []
    for i, c in enumerate(raw_chords):
        where = f"chords[{i}]"
        if not isinstance(c, dict) or not {"at_seconds", "chord"} <= c.keys():
            raise RawError(f"{where}: needs at_seconds and chord")
        chord = {"degree": "N"} if c["chord"] == "N" else read_label(c["chord"], tonic, mode, where)
        if changes and c["at_seconds"] <= changes[-1]["at_seconds"]:
            raise RawError(f"{where}: timestamps must increase")
        if changes and {k: v for k, v in changes[-1].items() if k != "at_seconds"} == chord:
            continue
        changes.append({"at_seconds": round(float(c["at_seconds"]), 3), **chord})
    if not changes:
        raise RawError("chords: empty")
    return changes


def chord_changes(segs, tonic, mode):
    return [{"at_seconds": round(s["start"], 3), "degree": to_degree(s["chord"], tonic, mode),
             "strength": round(strength(s), 3)} for s in segs]


def find_loop(changes, length=LOOP_LENGTH):
    """The most repeated run of `length` consecutive chords, or None if nothing repeats.

    Occurrences are counted without overlap; ties go to the pattern heard first.
    Runs containing N (no clear chord) are not considered.
    """
    starts = defaultdict(list)
    for i in range(len(changes) - length + 1):
        pattern = tuple(c["degree"] for c in changes[i:i + length])
        if "N" in pattern:
            continue
        if not starts[pattern] or i >= starts[pattern][-1] + length:
            starts[pattern].append(i)
    best = None
    for pattern, idx in starts.items():  # dict keeps first-heard order, so ties stay earliest
        if len(idx) >= 2 and (best is None or len(idx) > len(starts[best])):
            best = pattern
    if best is None:
        return None
    return {
        "degrees": list(best),
        "occurs_at_seconds": [changes[i]["at_seconds"] for i in starts[best]],
    }


# ---- key reading ---------------------------------------------------------------

def relative_of(tonic, mode):
    return ((tonic + 9) % 12, "minor") if mode == "major" else ((tonic + 3) % 12, "major")


def degree_at(changes, t):
    """The chord sounding at time t."""
    current = None
    for c in changes:
        if c["at_seconds"] > t:
            break
        current = c["degree"]
    return current


def most_heard(changes, duration):
    """The chord with the most total time, excluding N; earliest heard wins a tie."""
    total = defaultdict(float)
    for c, nxt in zip(changes, changes[1:] + [{"at_seconds": duration}]):
        if c["degree"] != "N":
            total[c["degree"]] += nxt["at_seconds"] - c["at_seconds"]
    if not total:
        return None
    degree = max(total, key=total.get)  # max keeps the first of equal values
    return {"degree": degree, "seconds": round(total[degree], 3)}


def key_reading(harmony, duration, section_ends=None, nudge=0.0, extra=()):
    """Weigh the key profiles and the chords themselves, and list every reading they support.

    The primary reading is the default profile's. Another reading is added when a
    different profile names it, or when the chords point to it: the most-heard chord
    is its tonic chord, or more than half of the section endings land on its tonic
    chord (only when there are at least MIN_SECTION_ENDINGS endings to count). A section's ending chord is the one sounding `nudge` seconds before its end.
    `ambiguous` is true whenever more than one reading is supported. `extra` adds
    readings named elsewhere, as (tonic letter, mode, reason), e.g. the key Moises shows.
    `duration` is where the last chord stops counting toward the most-heard chord.
    """
    tonic, mode = parse_key(harmony["key"], "key"), harmony["mode"]
    rel_tonic, rel_mode = relative_of(tonic, mode)
    profiles = harmony["key_reading"]["profiles"]
    changes = harmony["chord_changes"]

    readings = {}

    def support(key_pc, key_mode, reason):
        if key_pc == tonic and key_mode == mode:
            relation = "primary"
        elif key_pc == rel_tonic and key_mode == rel_mode:
            relation = "relative"
        else:
            relation = "other"
        r = readings.setdefault((key_pc, key_mode), {
            "key": NAMES[key_pc], "mode": key_mode, "relation": relation, "supported_by": []})
        r["supported_by"].append(reason)

    for p in profiles:
        support(parse_key(p["key"], f"key profile {p['profile']}"), p["mode"], f"{p['profile']} key profile")

    for key, key_mode, reason in extra:
        support(parse_key(key, reason), key_mode, reason)

    tonic_chord = "I" if mode == "major" else "i"
    relative_chord = "vi" if mode == "major" else "III"
    heard = most_heard(changes, duration)
    if heard and heard["degree"] == tonic_chord:
        support(tonic, mode, "most-heard chord")
    elif heard and heard["degree"] == relative_chord:
        support(rel_tonic, rel_mode, "most-heard chord")

    endings = None
    if section_ends:
        endings = [{"at_seconds": round(t, 3), "degree": degree_at(changes, t - nudge)} for t in section_ends]
        landed = [e["degree"] for e in endings]
        if len(landed) < MIN_SECTION_ENDINGS:
            pass
        elif landed.count(tonic_chord) * 2 > len(landed):
            support(tonic, mode, "chord at most section endings")
        elif landed.count(relative_chord) * 2 > len(landed):
            support(rel_tonic, rel_mode, "chord at most section endings")

    ordered = sorted(readings.values(), key=lambda r: ["primary", "relative", "other"].index(r["relation"]))
    reading = {
        "profiles": profiles,
        "relative": {"key": NAMES[rel_tonic], "mode": rel_mode},
        "readings": ordered,
        "ambiguous": len(ordered) > 1,
    }
    if heard:
        reading["most_heard"] = heard
    if endings is not None:
        reading["section_endings"] = endings
    return reading


# ---- assembly ----------------------------------------------------------------

def require(raw, keys):
    missing = [k for k in keys if k not in raw]
    if missing:
        raise RawError(f"raw input is missing {', '.join(missing)}")


def convert(raw, min_chord_beats=MIN_CHORD_BEATS):
    """Returns (data, merge_log, segments_before_merge)."""
    require(raw, ["code", "duration_seconds", "analysed_on", "pipeline",
                  "key", "scale", "key_strength", "key_profiles", "bpm", "beats_seconds",
                  "beat_confidence", "beat_confidence_scale_max", "chords"])

    tonic = parse_key(raw["key"], "key")
    if raw["scale"] not in NUMERALS:
        raise RawError(f"scale: expected major or minor, got {raw['scale']!r}")
    mode = raw["scale"]

    track = {k: raw[k] for k in ("code", "duration_seconds", "analysed_on", "pipeline")}
    if raw.get("notes"):
        track["notes"] = raw["notes"]

    if raw.get("chord_detector") == "chordino":
        # Chordino smooths its own output and gives no strength, so nothing is merged
        changes, log, before = labelled_changes(raw["chords"], tonic, mode), [], []
        source, chord_filter = {"tool": "Chordino", "method": raw["pipeline"],
                                "covers_seconds": [0, raw["duration_seconds"]]}, None
    else:
        before = segments(raw["chords"], raw["duration_seconds"])
        if not before:
            raise RawError("chords: empty")
        min_seconds = min_chord_beats * 60.0 / raw["bpm"]
        max_strength = statistics.median(strength(s) for s in before)
        after, log = merge_short_chords(before, min_seconds, max_strength)
        changes = chord_changes(after, tonic, mode)
        source = {"tool": "Essentia", "method": raw["pipeline"], "covers_seconds": [0, raw["duration_seconds"]]}
        chord_filter = {
            "rule": (f"A chord shorter than {min_chord_beats:g} of a beat and weaker than this track's "
                     "median chord strength is absorbed into the longer of its two neighbours, "
                     "shortest first."),
            "min_duration_seconds": round(min_seconds, 3),
            "max_strength": round(max_strength, 3),
            "segments_merged": len(log),
        }

    harmony = {
        "available": True,
        "key": raw["key"],
        "mode": mode,
        "key_confidence": raw["key_strength"],
        "key_reading": {"profiles": [
            {"profile": p["profile"], "key": p["key"], "mode": p["scale"], "strength": p["strength"]}
            for p in raw["key_profiles"]]},
        "chord_changes": changes,
        "chord_source": source,
    }
    if chord_filter:
        harmony["chord_filter"] = chord_filter
    harmony["key_reading"] = key_reading(harmony, raw["duration_seconds"])
    loop = find_loop(changes)
    if loop:
        harmony["loop"] = loop

    groove = {
        "available": True,
        "bpm": raw["bpm"],
        "beat_confidence": {"value": raw["beat_confidence"], "scale_max": raw["beat_confidence_scale_max"]},
        "beats_seconds": [round(float(t), 3) for t in raw["beats_seconds"]],
    }

    data = {
        "track": track,
        "music": {
            "harmony": harmony,
            "groove": groove,
            "melody": {"available": False, "reason_if_unavailable": MELODY_REASON},
        },
    }
    return data, log, before


def chord_changes_per_beat(changes, beats, start, end):
    """Chord changes per beat inside [start, end). Used by the structure step, per section."""
    n_beats = sum(start <= b < end for b in beats)
    if n_beats == 0:
        return None
    n_changes = sum(start <= c["at_seconds"] < end for c in changes[1:])
    return round(n_changes / n_beats, 3)


def describe(segs, tonic, mode):
    return "\n".join(f"  {s['start']:8.3f}s  {to_degree(s['chord'], tonic, mode):5s} "
                     f"{s['end'] - s['start']:6.3f}s  strength {strength(s):.3f}" for s in segs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("raw")
    parser.add_argument("out")
    parser.add_argument("--min-chord-beats", type=float, default=MIN_CHORD_BEATS,
                        help=f"merge threshold as a fraction of a beat (default {MIN_CHORD_BEATS})")
    parser.add_argument("--show-chords", action="store_true", help="print the chord list before and after merging")
    args = parser.parse_args()

    raw_path, out_path = Path(args.raw), Path(args.out)
    raw = json.loads(raw_path.read_text())
    try:
        data, log, before = convert(raw, args.min_chord_beats)
    except RawError as e:
        print(f"REFUSING TO CONVERT {raw_path}: {e}", file=sys.stderr)
        return 1

    h = data["music"]["harmony"]
    tonic = parse_key(h["key"], "key")
    f = h.get("chord_filter")
    if f is None:
        print(f"{len(h['chord_changes'])} chord changes from {h['chord_source']['tool']}; nothing merged")
        if args.show_chords:
            print("\n".join(f"  {c['at_seconds']:8.3f}s  {c['degree']}{c.get('detail', '')}"
                            f"{'/' + c['bass_degree'] if 'bass_degree' in c else ''}" for c in h["chord_changes"]))
    else:
        print(f"{len(before)} chords before merging, {len(h['chord_changes'])} after; "
              f"threshold {f['min_duration_seconds']}s and strength < {f['max_strength']}")
    for m in log:
        print(f"  merged {to_degree(m['chord'], tonic, h['mode']):5s} at {m['start']:8.3f}s "
              f"({m['seconds']:.3f}s, strength {m['strength']:.3f}) into "
              f"{to_degree(m['into'], tonic, h['mode'])}")
    if args.show_chords and f is not None:
        print("BEFORE\n" + describe(before, tonic, h["mode"]))
        ends = [c["at_seconds"] for c in h["chord_changes"][1:]] + [raw["duration_seconds"]]
        print("AFTER\n" + "\n".join(f"  {c['at_seconds']:8.3f}s  {c['degree']:5s} {e - c['at_seconds']:6.3f}s  "
                                     f"strength {c['strength']:.3f}" for c, e in zip(h["chord_changes"], ends)))
    kr = h["key_reading"]
    print("key readings:", "; ".join(f"{r['key']} {r['mode']} ({r['relation']}: {', '.join(r['supported_by'])})"
                                     for r in kr["readings"]), "| ambiguous" if kr["ambiguous"] else "")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
