#!/usr/bin/env python3
"""Compare one track's structure with the Harmonix Set.

    python scripts/harmonix.py data/p01.json [--top 5]

Run after billboard.py. Adds the best Harmonix matches to `comparisons.matches` and a
corpus statement to `population_context.statements`, replacing any earlier Harmonix
entries and leaving other sources alone.

Corpus: corpus/harmonix/ (MIT licence; github.com/urinieto/harmonixset at commit
64abeb5, see download/PROVENANCE.txt). 912 Western pop songs with hand-annotated
section boundaries, beats and downbeats. It has no chords, so harmony is always
unavailable and no overall similarity is given. Its metadata has no release dates,
so matches carry no year.

Structure is compared exactly as in billboard.py: both songs become a list of section
lengths in bars, aligned in order, with sections lining up when their lengths are
within STRUCTURE_TOLERANCE_BARS. Section labels are ignored. A Harmonix section's
length is its annotated beats divided by the song's beats per bar. Silence before
or after the music is left out.
"""
import argparse
import csv
import json
import statistics
from pathlib import Path

from billboard import ROOT, structure_dimension, track_sections

CORPUS = ROOT / "corpus" / "harmonix"
SOURCE = "Harmonix"
HARMONY_REASON = "The Harmonix Set has no chord annotations, so harmony can't be compared."
SKIP = {"silence", "end"}


def parse_song(stem):
    beats = []
    for line in (CORPUS / "beats_and_downbeats" / f"{stem}.txt").read_text().splitlines():
        if line.strip():
            t, pos, _bar = line.split()[:3]
            beats.append((float(t), int(float(pos))))
    per_bar = statistics.median(
        prev for (_, prev), (_, pos) in zip(beats, beats[1:]) if pos == 1 and prev > 1) if beats else 4
    marks = []
    for line in (CORPUS / "segments" / f"{stem}.txt").read_text().splitlines():
        if line.strip():
            t, label = line.split(maxsplit=1)
            marks.append((float(t), label.strip()))
    sections = []
    for (start, label), (end, _) in zip(marks, marks[1:]):
        if label in SKIP or end <= start:
            continue
        n = sum(start <= t < end for t, _ in beats)
        if n:
            sections.append((start, end, round(n / per_bar * 4) / 4))
    return sections, (marks[-1][0] if marks else 0.0)


def load_corpus():
    songs = []
    with open(CORPUS / "metadata.csv", newline="") as f:
        for row in csv.DictReader(f):
            sections, end = parse_song(row["File"])
            songs.append({"title": row["Title"].strip(), "artist": row["Artist"].strip(),
                          "sections": sections, "end": end})
    return songs


def basis(songs):
    return (f"Harmonix Set: {len(songs)} Western pop songs with sections, beats and downbeats annotated by hand "
            "(Nieto et al. 2019). The corpus gives no release dates. No chords, so it is compared on "
            "structure only.")


def section_statement(track_secs, songs):
    counts = [len(s["sections"]) for s in songs if s["sections"]]
    lo, hi = sorted(counts)[len(counts) // 4], sorted(counts)[3 * len(counts) // 4]
    return {
        "statement": (f"The analysis divides your song into {len(track_secs)} parts. Half of the Harmonix songs "
                      f"have between {lo} and {hi} annotated parts; the middle value is "
                      f"{statistics.median(counts):g}."),
        "basis": basis(songs),
    }


def compare(data, top):
    music = data["music"]
    structure, groove = music["structure"], music["groove"]
    songs = load_corpus()
    if not structure.get("available"):
        raise SystemExit("this track's structure is unavailable; nothing to compare with Harmonix")
    secs = track_sections(structure, groove["beats_seconds"])

    scored = []
    for song in songs:
        dim = structure_dimension(secs, song)
        match = {"source": SOURCE, "title": song["title"], "artist": song["artist"],
                 "dimensions": {"harmony": {"available": False, "reason_if_unavailable": HARMONY_REASON},
                                "structure": dim}}
        scored.append((dim["score"] if dim["available"] else 0, match))
    scored.sort(key=lambda x: -x[0])
    best = [m for _, m in scored[:top]]

    comparisons = data.get("comparisons") or {"available": True, "matches": []}
    others = [m for m in comparisons.get("matches", []) if m["source"] != SOURCE]
    data["comparisons"] = {"available": True, "matches": others + best}

    pc = data.get("population_context") or {"available": True, "statements": []}
    kept = [s for s in pc.get("statements", []) if not s["basis"].startswith("Harmonix Set")]
    data["population_context"] = {"available": True, "statements": kept + [section_statement(secs, songs)]}
    return data, len(songs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()
    path = Path(args.data)
    data, n = compare(json.loads(path.read_text()), args.top)
    print(f"compared with {n} Harmonix songs")
    for m in data["comparisons"]["matches"]:
        if m["source"] == SOURCE:
            d = m["dimensions"]["structure"]
            print(f"\n{d['score'] if d['available'] else '-'}  {m['title']} — {m['artist']}\n  "
                  f"{d['evidence'] if d['available'] else d['reason_if_unavailable']}")
    for s in data["population_context"]["statements"]:
        if s["basis"].startswith("Harmonix Set"):
            print(f"\n{s['statement']}\n  ({s['basis']})")
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\nupdated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
