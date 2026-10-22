#!/usr/bin/env python3
"""Put the Moises chord reading into data/<code>.json in place of Essentia's chords.

    python scripts/moises.py reference/p01.moises.json data/p01.json

Moises is the chord source for every track. Run this after convert.py and
structure.py. It replaces `music.harmony.chord_changes` with the chords read from
the Moises chord chart, turned into scale degrees, and redoes everything that
depends on them: the loop, the most-heard chord, the chords at section endings and
the chord-change rate per section.

Essentia still provides the key and its confidence, the beats and the sections. If
the key Moises shows is not Essentia's, the key reading lists both and is marked
ambiguous. The scale degrees are always counted from Essentia's key.

Moises shows no chord strength, so none is written. Nothing is merged, so there is
no chord_filter. Chords are only placed inside the stretch Moises showed
(`covers_seconds`). Section figures that would need chords outside that stretch are
left out rather than guessed.

The reference file is written by hand from the Moises chord chart; see
reference/p01.moises.json for the shape. Any label this script can't read is an
error, not a guess.
"""
import json
import re
import sys
from pathlib import Path

from convert import RawError, chord_changes_per_beat, find_loop, key_reading, parse_key, read_label

def moises_key(shown):
    """'G' -> ('G', 'major'); 'Em' -> ('E', 'minor'). Moises writes minor keys with an m."""
    m = re.match(r"^([A-G][#b]?)(m?)$", str(shown))
    if not m:
        raise RawError(f"displayed_key: cannot read {shown!r}")
    return m.group(1), "minor" if m.group(2) else "major"


def apply(ref, data):
    track, music = data["track"], data["music"]
    if ref.get("code") != track["code"]:
        raise RawError(f"code: reference is {ref.get('code')!r}, data is {track['code']!r}")
    harmony = music["harmony"]
    if not harmony.get("available"):
        raise RawError("music.harmony is unavailable; run convert.py first")
    tonic, mode = parse_key(harmony["key"], "music.harmony.key"), harmony["mode"]

    lo, hi = ref["excerpt"]["approx_seconds"]
    hi = min(hi, track["duration_seconds"])
    changes = []
    for i, c in enumerate(ref["chord_changes"]):
        where = f"chord_changes[{i}]"
        if not lo <= c["approx_seconds"] < hi:
            raise RawError(f"{where}: {c['approx_seconds']}s is outside the excerpt {lo}-{hi}s")
        changes.append({"at_seconds": c["approx_seconds"], **read_label(c["label"], tonic, mode, where)})

    source = {
        "tool": "Moises",
        "observed_on": ref["observed_on"],
        "method": f"{ref['source']}. {ref['method']}",
        "covers_seconds": [lo, hi],
    }
    if hi < track["duration_seconds"]:
        if not ref.get("beyond_coverage"):
            raise RawError("beyond_coverage: the chords stop before the track ends; say why")
        source["beyond_coverage"] = ref["beyond_coverage"]

    harmony["chord_changes"] = changes
    harmony["chord_source"] = source
    harmony.pop("chord_filter", None)
    loop = find_loop(changes)
    if loop:
        harmony["loop"] = loop
    else:
        harmony.pop("loop", None)

    groove = music.get("groove", {})
    structure = music.get("structure", {})
    sections = structure.get("sections", []) if structure.get("available") else []
    for s in sections:
        s.pop("chord_changes_per_beat", None)
        if s["end_seconds"] <= hi and groove.get("available"):
            rate = chord_changes_per_beat(changes, groove["beats_seconds"], s["start_seconds"], s["end_seconds"])
            if rate is not None:
                s["chord_changes_per_beat"] = rate
    ends = [s["end_seconds"] for s in sections if s["end_seconds"] <= hi]
    nudge = 30.0 / groove["bpm"] if groove.get("available") else 0.0
    shown_key, shown_mode = moises_key(ref["displayed_key"])
    harmony["key_reading"] = key_reading(harmony, hi, ends or None, nudge,
                                         extra=[(shown_key, shown_mode, "key shown by Moises")])
    # analyse.py ends the pipeline with "; chords: <Essentia detector>"; Moises replaces that clause
    track["pipeline"] = re.sub(r"; chords: .*$", "", track["pipeline"]) + \
        f"; chords: Moises chord chart, read {ref['observed_on']}"
    return data


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    ref_path, data_path = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        data = apply(json.loads(ref_path.read_text()), json.loads(data_path.read_text()))
    except (RawError, KeyError) as e:
        print(f"REFUSING TO APPLY {ref_path}: {e}", file=sys.stderr)
        return 1
    h = data["music"]["harmony"]
    print(f"{len(h['chord_changes'])} Moises chord changes, {h['chord_source']['covers_seconds'][0]}-"
          f"{h['chord_source']['covers_seconds'][1]}s")
    print("  " + " ".join(c["degree"] + (c.get("detail") or "") + (f"/{c['bass_degree']}" if "bass_degree" in c else "")
                          for c in h["chord_changes"]))
    if "loop" in h:
        print(f"loop {'-'.join(h['loop']['degrees'])} at " + ", ".join(f"{t}s" for t in h["loop"]["occurs_at_seconds"]))
    kr = h["key_reading"]
    print("key readings:", "; ".join(f"{r['key']} {r['mode']} ({', '.join(r['supported_by'])})"
                                     for r in kr["readings"]), "| ambiguous" if kr["ambiguous"] else "")
    data_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"updated {data_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
