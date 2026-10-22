#!/usr/bin/env python3
"""Compare one track with the McGill Billboard corpus, on harmony and on structure.

    python scripts/billboard.py data/p01.json [--top 5]

Run after moises.py. Adds the best Billboard matches to `comparisons.matches` and a
corpus statement to `population_context.statements`, replacing any earlier
Billboard entries and leaving other sources alone.

Corpus: corpus/billboard/ (CC0). billboard-2.0-index.csv gives titles, artists and
chart dates. annotations/McGill-Billboard/<id>/salami_chords.txt gives hand-annotated
chords and sections with timestamps. Songs that appear more than once in the index
are compared once (lowest id).

Harmony. Both songs become a list of chord moves. A move is the distance from one
chord root to the next, in semitones, plus whether the chord it lands on is major or
minor. Moves don't depend on the key, so the comparison holds whichever key reading
is right. Chords are reduced to major or minor triads first. Chords with no third
(sus, power chords) and no-chord stretches never match. The best local alignment
(Smith-Waterman: match +1, mismatch -1, gap -1) of this track's moves inside each
song is found. Within that alignment, the stretch of HARMONY_WINDOW_MOVES consecutive
moves of this track with the most lined-up moves is kept; the score is the share of
that stretch that lines up (the whole track if it has fewer moves). Only the part of
the track the chord source covers is used.

Structure. Both songs become a list of section lengths in bars. This track's sections
come from structure.py (bars = beats / 4). Billboard's come from its annotated
sections; their names are ignored. Two sections line up when their lengths differ by
at most STRUCTURE_TOLERANCE_BARS. The same alignment is used, and the score is the
share of this track's sections that line up.

Overall similarity is the mean of the two scores. Matches are ranked by it.
Every evidence sentence is generated here from the aligned stretch, with times in
both songs.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

from convert import NUMERALS, parse_key

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "billboard"
INDEX = CORPUS / "download" / "billboard-2.0-index.csv"
ANNOTATIONS = CORPUS / "annotations" / "McGill-Billboard"
SOURCE = "McGill Billboard"
STRUCTURE_TOLERANCE_BARS = 1.0
# Harmony is scored on the best stretch of this many consecutive chord moves in your song
# (about four times round a four-chord loop), so the score doesn't shrink as songs get longer.
HARMONY_WINDOW_MOVES = 16
MATCH, MISMATCH, GAP = 1, -1, -1
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NO_CHORD = {"N", "*", "&pause", "X"}
METRE = re.compile(r"^\((\d+)/(\d+)\)$")


# ---- reading the corpus -----------------------------------------------------------

def chord_of(token):
    """'A:min7/b3' -> (9, 'min'); 'C:sus4' -> (0, 'other'); 'N' -> None."""
    if token in NO_CHORD:
        return None
    m = re.match(r"^([A-G])([#b]*):([^/]*)", token)
    if not m:
        raise ValueError(f"cannot read chord {token!r}")
    letter, acc, quality = m.groups()
    root = (NOTE[letter] + acc.count("#") - acc.count("b")) % 12
    base = re.sub(r"\(.*", "", quality)
    if base.startswith(("min", "hdim", "dim")):
        return root, "min"
    if base.startswith(("maj", "aug")) or base[:1].isdigit() and base not in ("1", "5"):
        return root, "maj"
    return root, "other"  # sus chords, power chords (5) and single notes (1): no third


def parse_song(path):
    """Chord changes [(seconds, chord)] and sections [(start, end, bars)] of one annotation."""
    lines, metre = [], 1.0
    for raw in path.read_text(errors="replace").splitlines():
        m = re.match(r"^# metre: (\d+)/(\d+)", raw)
        if m and not lines:
            metre = int(m.group(1)) / int(m.group(2))
        if not raw.strip() or raw.startswith("#"):
            continue
        t, _, rest = raw.partition("\t")
        lines.append((float(t), rest.strip()))
    chords, sections, open_section = [], [], None
    for (t, rest), nxt in zip(lines, lines[1:] + [(None, "")]):
        t_next = nxt[0]
        label = re.match(r"^([A-Z]'*),", rest)
        if label or rest in ("end", "silence") or t_next is None:
            if open_section:
                sections.append((open_section[0], t, open_section[1]))
                open_section = None
            if label:
                open_section = [t, 0.0]
        if "|" not in rest or t_next is None:
            if "|" not in rest and rest.startswith("silence"):
                chords.append((t, None))
            continue
        body = rest[rest.index("|"):rest.rindex("|") + 1]
        times = re.search(r"\|\s*x(\d+)", rest[rest.rindex("|"):])
        bars = [b.split() for b in body.strip("|").split("|")] * (int(times.group(1)) if times else 1)
        if open_section:
            # a bar marked with its own metre, e.g. (2/4), counts as that fraction of a normal bar
            open_section[1] += sum(bar_weight(bar, metre) for bar in bars)
        bars = [[tok for tok in bar if not METRE.match(tok)] for bar in bars]
        bar_len = (t_next - t) / len(bars)
        prev = None
        for i, bar in enumerate(bars):
            for j, tok in enumerate(bar):
                tok = prev if tok == "." else tok
                prev = tok
                chords.append((t + bar_len * (i + j / len(bar)), chord_of(tok)))
    if open_section:
        sections.append((open_section[0], lines[-1][0], open_section[1]))
    end = lines[-1][0] if lines else 0.0
    return collapse(chords), [s for s in sections if s[2] > 0], end


def bar_weight(bar, metre):
    for tok in bar:
        m = METRE.match(tok)
        if m:
            return int(m.group(1)) / int(m.group(2)) / metre
    return 1.0


def collapse(chords):
    out = []
    for t, c in chords:
        if not out or out[-1][1] != c:
            out.append((t, c))
    return out


def load_corpus():
    songs, seen = [], set()
    with open(INDEX, newline="") as f:
        for row in csv.DictReader(f):
            if not row["title"]:
                continue
            path = ANNOTATIONS / f"{int(row['id']):04d}" / "salami_chords.txt"
            key = (row["title"].strip().lower(), row["artist"].strip().lower())
            if key in seen or not path.exists():
                continue
            seen.add(key)
            chords, sections, end = parse_song(path)
            songs.append({"id": row["id"], "title": row["title"].strip(), "artist": row["artist"].strip(),
                          "year": int(row["chart_date"][:4]), "chords": chords, "sections": sections, "end": end})
    return songs


# ---- this track ---------------------------------------------------------------------

def degree_chord(degree, mode):
    """'vi' in major -> (9, 'min'); 'N' -> None."""
    if degree == "N":
        return None
    upper = degree[0] + degree[1:].upper() if degree[0] in "b#" else degree.upper()
    quality = "maj" if degree.lstrip("b#")[0].isupper() else "min"
    return NUMERALS[mode].index(upper), quality


def track_chords(harmony):
    mode = harmony["mode"]
    return collapse([(c["at_seconds"], degree_chord(c["degree"], mode)) for c in harmony["chord_changes"]])


def track_sections(structure, beats):
    out = []
    for s in structure["sections"]:
        n = sum(s["start_seconds"] <= b < s["end_seconds"] for b in beats)
        out.append((s["start_seconds"], s["end_seconds"], n / 4))
    return out


# ---- alignment ------------------------------------------------------------------------

def moves(chords):
    """One move per chord change: (semitones from the previous root, quality landed on)."""
    out = []
    for (_, a), (_, b) in zip(chords, chords[1:]):
        if a is None or b is None or b[1] == "other" or a[1] == "other":
            out.append(None)
        else:
            out.append(((b[0] - a[0]) % 12, b[1]))
    return out


def align(query, target, same):
    """Best local alignment. Returns (matches, [(qi, ti) matched pairs])."""
    rows, cols = len(query) + 1, len(target) + 1
    score = [[0] * cols for _ in range(rows)]
    best, at = 0, (0, 0)
    for i in range(1, rows):
        q, row, up = query[i - 1], score[i], score[i - 1]
        for j in range(1, cols):
            s = max(0, up[j - 1] + (MATCH if same(q, target[j - 1]) else MISMATCH), up[j] + GAP, row[j - 1] + GAP)
            row[j] = s
            if s > best:
                best, at = s, (i, j)
    pairs, (i, j) = [], at
    while i > 0 and j > 0 and score[i][j] > 0:
        if score[i][j] == score[i - 1][j - 1] + (MATCH if same(query[i - 1], target[j - 1]) else MISMATCH):
            if same(query[i - 1], target[j - 1]):
                pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif score[i][j] == score[i - 1][j] + GAP:
            i -= 1
        else:
            j -= 1
    return len(pairs), pairs[::-1]


def same_move(a, b):
    return a is not None and a == b


def same_length(a, b):
    return abs(a - b) <= STRUCTURE_TOLERANCE_BARS


# ---- evidence -------------------------------------------------------------------------

def clock(seconds):
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def bars(n):
    return f"{n:g}" if n == int(n) else f"{n:.1f}"


def harmony_dimension(track, track_end, degrees, song):
    query, target = moves(track), moves(song["chords"])
    if not any(query):
        return {"available": False, "reason_if_unavailable": "Your song has no chord moves to compare."}
    n, pairs = align(query, target, same_move)
    if n == 0:
        return {"available": False, "reason_if_unavailable": "No chord move in your song lines up with this one."}
    width = min(HARMONY_WINDOW_MOVES, len(query))
    # densest stretch of `width` consecutive moves of this track within the alignment (earliest on a tie)
    start = max(range(max(1, len(query) - width + 1)),
                key=lambda w: (sum(w <= q < w + width for q, _ in pairs), -w))
    pairs = [(q, t) for q, t in pairs if start <= q < start + width]
    n = len(pairs)
    q0, q1 = pairs[0][0], pairs[-1][0]
    t0, t1 = pairs[0][1], pairs[-1][1]
    here = [track[q0][0], track[q1 + 2][0] if q1 + 2 < len(track) else track_end]
    there = [song["chords"][t0][0],
             song["chords"][t1 + 2][0] if t1 + 2 < len(song["chords"]) else song["end"]]
    run = degrees[q0:q1 + 2]
    shown = " → ".join(run[:9]) + (" → …" if len(run) > 9 else "")
    return {
        "available": True,
        "score": round(n / width, 3),
        "evidence": (f"In the best-matching stretch of {width} chord moves in your song, {n} line up, in order, "
                     f"with {song['title']}: around {clock(here[0])}–{clock(here[1])} in yours and "
                     f"{clock(there[0])}–{clock(there[1])} in theirs. The roots step the same distances and land on "
                     f"major or minor chords in the same places. In yours that stretch runs {shown}"
                     + ("" if shown.endswith("…") else ".")),
        "this_track_seconds": [round(x, 3) for x in here],
        "reference_seconds": [round(x, 3) for x in there],
    }


def structure_dimension(track_secs, song):
    query, target = [s[2] for s in track_secs], [s[2] for s in song["sections"]]
    if not target:
        return {"available": False, "reason_if_unavailable": "This song has no annotated parts."}
    n, pairs = align(query, target, same_length)
    if n == 0:
        return {"available": False,
                "reason_if_unavailable": "No run of parts in your song has lengths close to this one's."}
    q0, q1 = pairs[0][0], pairs[-1][0]
    t0, t1 = pairs[0][1], pairs[-1][1]
    here = [track_secs[q0][0], track_secs[q1][1]]
    there = [song["sections"][t0][0], song["sections"][t1][1]]
    mine = ", ".join(bars(track_secs[q][2]) for q, _ in pairs)
    theirs = ", ".join(bars(song["sections"][t][2]) for _, t in pairs)
    return {
        "available": True,
        "score": round(n / len(query), 3),
        "evidence": (f"{n} of the {len(query)} parts of your song line up, in order, with parts of {song['title']} "
                     f"that are within {bars(STRUCTURE_TOLERANCE_BARS)} bar of the same length: around "
                     f"{clock(here[0])}–{clock(here[1])} in yours and {clock(there[0])}–{clock(there[1])} in theirs. "
                     f"Lengths in bars, yours: {mine}; theirs: {theirs}."),
        "this_track_seconds": [round(x, 3) for x in here],
        "reference_seconds": [round(x, 3) for x in there],
    }


# ---- population context ------------------------------------------------------------

def loop_statement(harmony, songs, years):
    loop = harmony.get("loop")
    if not loop:
        return None
    chords = [degree_chord(d, harmony["mode"]) for d in loop["degrees"]]
    pattern = moves([(0, c) for c in chords])
    if None in pattern:
        return None
    k = len(pattern)
    hits = sum(any(m[i:i + k] == pattern for i in range(len(m) - k + 1)) for m in (moves(s["chords"]) for s in songs))
    return {
        "statement": (f"{hits} of {len(songs)} Billboard songs ({hits / len(songs):.0%}) move between chords the "
                      f"way your repeating {' → '.join(loop['degrees'])} does, at least once."),
        "basis": basis(songs, years),
    }


def basis(songs, years):
    return (f"McGill Billboard corpus: {len(songs)} distinct songs sampled from the US Billboard Hot 100, "
            f"charting {min(years)}–{max(years)}, with chords and sections annotated by hand. "
            "Matching uses chord moves, so it does not depend on the key.")


# ---- entry ---------------------------------------------------------------------------

def compare(data, top):
    music = data["music"]
    harmony, structure, groove = music["harmony"], music["structure"], music["groove"]
    songs = load_corpus()
    years = [s["year"] for s in songs]
    track = track_chords(harmony)
    track_end = harmony["chord_source"]["covers_seconds"][1]
    degrees = []
    for c in harmony["chord_changes"]:
        if not degrees or degrees[-1] != c["degree"]:
            degrees.append(c["degree"])
    secs = track_sections(structure, groove["beats_seconds"]) if structure.get("available") else []

    scored = []
    for song in songs:
        dims = {"harmony": harmony_dimension(track, track_end, degrees, song),
                "structure": structure_dimension(secs, song) if secs else
                {"available": False, "reason_if_unavailable": "The shape of your song is unavailable."}}
        live = [d["score"] for d in dims.values() if d["available"]]
        match = {"source": SOURCE, "title": song["title"], "artist": song["artist"], "year": song["year"],
                 "dimensions": dims}
        if len(live) >= 2:
            match["overall_similarity"] = round(sum(live) / len(live), 3)
        scored.append((match.get("overall_similarity", 0), match))
    scored.sort(key=lambda x: -x[0])
    best = [m for _, m in scored[:top]]

    comparisons = data.get("comparisons") or {"available": True, "matches": []}
    others = [m for m in comparisons.get("matches", []) if m["source"] != SOURCE]
    data["comparisons"] = {"available": True, "matches": others + best}

    pc = data.get("population_context") or {"available": True, "statements": []}
    kept = [s for s in pc.get("statements", []) if not s["basis"].startswith("McGill Billboard")]
    stmt = loop_statement(harmony, songs, years)
    statements = kept + ([stmt] if stmt else [])
    data["population_context"] = ({"available": True, "statements": statements} if statements else
                                  {"available": False, "reason_if_unavailable": "No corpus statement could be made."})
    return data, len(songs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()
    path = Path(args.data)
    data, n = compare(json.loads(path.read_text()), args.top)
    print(f"compared with {n} Billboard songs")
    for m in data["comparisons"]["matches"]:
        if m["source"] != SOURCE:
            continue
        print(f"\n{m.get('overall_similarity', '-')}  {m['title']} — {m['artist']} ({m['year']})")
        for name, d in m["dimensions"].items():
            print(f"  {name}: {d['score'] if d['available'] else 'unavailable'}  "
                  f"{d['evidence'] if d['available'] else d['reason_if_unavailable']}")
    for s in data["population_context"].get("statements", []):
        print(f"\n{s['statement']}\n  ({s['basis']})")
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\nupdated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
