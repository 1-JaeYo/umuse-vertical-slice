#!/usr/bin/env python3
"""Find section boundaries and returning material from the chroma frames.

    python scripts/structure.py raw/kene.raw.json data/kene.json

Reads the chroma (HPCP) frames that scripts/analyse.py keeps, and updates the data
file written by scripts/convert.py in place: adds `music.structure`, the chord-change
rate per section, and the section-ending chords to the key reading.

Method, all deterministic, with every setting written into `music.structure.settings`:

1. Beat-synchronous chroma: average the frames within each beat, so the matrix is
   cleaner and boundaries survive tempo drift. Each beat vector is unit-normalised.
2. Self-similarity matrix: cosine similarity between short runs of EMBED_BEATS beats
   centred on each beat, kept as a repetition matrix of mutual nearest neighbours
   (each beat's closest NEIGHBOUR_FRACTION of the track).
3. Novelty from repetition, after Serra et al. 2014 ("structure features"): the matrix
   is reread by time lag and smoothed, and novelty is how much the pattern of
   repetitions changes from one beat to the next. This finds where a repeated passage
   starts or stops, which a sound-contrast kernel (Foote 2000) misses when two
   sections use the same notes. Boundaries are novelty peaks that are the highest
   point within MIN_SECTION_BEATS either side and above the curve's mean plus half a
   standard deviation.
4. Short parts: a part shorter than MIN_PART_BEATS is merged into the neighbour whose
   average chroma it is closest to (cosine), shortest first, until none is left.
5. Repeats: for each section's opening RETURN_BEATS (the whole section if shorter), slide its block of beats along everything after it and
   take the mean similarity along the diagonal. A position counts as a return when
   that mean reaches the 90th percentile of all pairwise beat similarities in the
   track; overlapping returns keep the strongest.

Sections are not named. Boundaries and returns are snapped to beats.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

from convert import chord_changes_per_beat, key_reading

EMBED_BEATS = 4            # length of the beat runs compared in step 2
NEIGHBOUR_FRACTION = 0.1   # share of the track kept as each beat's nearest neighbours
SMOOTH_BEATS = 4           # Gaussian smoothing of the lag matrix along time
MIN_SECTION_BEATS = 8      # peak-picking neighbourhood: boundaries at least this far apart
# Shortest part kept: 4 bars. Hand-annotated parts shorter than 4 bars are rare (4.0% of
# 9448 in Harmonix, 5.6% of 7136 in Billboard), so a shorter one is merged (step 4).
MIN_PART_BEATS = 16
PEAK_STD = 0.5             # boundary threshold: mean + PEAK_STD * std of novelty
REPEAT_PERCENTILE = 90     # return threshold: percentile of similarities between all pairs of
                           # RETURN_BEATS-long stretches (the same length as what is compared)
RETURN_BEATS = 16          # how much of a part's opening is searched for later returns (4 bars)
FRAME_CENTRE_SECONDS = 2048 / 44100  # half of TonalExtractor's 4096-sample frame


def beat_chroma(frames, hop, edges):
    """Mean chroma per beat interval [edges[k], edges[k+1]), unit-normalised."""
    frames = np.asarray(frames, dtype=float)
    centres = np.arange(len(frames)) * hop + FRAME_CENTRE_SECONDS
    rows = []
    for a, b in zip(edges, edges[1:]):
        inside = (centres >= a) & (centres < b)
        if inside.any():
            rows.append(frames[inside].mean(axis=0))
        else:  # beat shorter than a frame hop: take the nearest frame
            rows.append(frames[min(len(frames) - 1, int(round(((a + b) / 2) / hop)))])
    x = np.array(rows)
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return np.divide(x, norms, out=np.zeros_like(x), where=norms > 0)


def embed(x, m):
    """Each beat's vector becomes the run of m beats centred on it, unit-normalised."""
    n = len(x)
    stacked = np.hstack([x[np.clip(np.arange(n) + k, 0, n - 1)] for k in range(-(m // 2), m - m // 2)])
    norms = np.linalg.norm(stacked, axis=1, keepdims=True)
    return np.divide(stacked, norms, out=np.zeros_like(stacked), where=norms > 0)


def repetition_matrix(x, fraction):
    """1 where two beats are each among the other's nearest neighbours, else 0."""
    sim = x @ x.T
    np.fill_diagonal(sim, -np.inf)
    k = max(1, int(round(fraction * len(sim))))
    near = np.zeros(sim.shape, dtype=bool)
    rows = np.arange(len(sim))[:, None]
    near[rows, np.argsort(-sim, axis=1)[:, :k]] = True
    return (near & near.T).astype(float)


def novelty(rep, smooth):
    """Change in the smoothed time-lag repetition pattern from one beat to the next."""
    lag = np.array([np.roll(rep[i], -i) for i in range(len(rep))])
    lag = gaussian_filter(lag, sigma=(smooth, 0.5))
    curve = np.r_[0.0, np.sum(np.diff(lag, axis=0) ** 2, axis=1)]
    return curve / curve.max() if curve.max() > 0 else curve


def boundaries(curve, min_gap, std_factor):
    threshold = curve.mean() + std_factor * curve.std()
    peaks = []
    for k in range(min_gap, len(curve) - min_gap):
        window = curve[k - min_gap:k + min_gap + 1]
        if curve[k] >= threshold and curve[k] == window.max():
            if not peaks or k - peaks[-1] >= min_gap:
                peaks.append(k)
    return peaks, threshold


def merge_short(peaks, x, n, min_beats):
    """Remove boundaries until every part is at least min_beats long.

    The shortest part goes first (earliest on a tie) and joins whichever neighbour it
    sounds more like: the cosine between the parts' average beat chroma.
    """
    bounds = [0, *peaks, n]

    def centre(a, b):
        v = x[a:b].mean(axis=0)
        norm = np.linalg.norm(v)
        return v / norm if norm else v

    while len(bounds) > 2:
        parts = list(zip(bounds, bounds[1:]))
        short = [i for i, (a, b) in enumerate(parts) if b - a < min_beats]
        if not short:
            break
        i = min(short, key=lambda k: (parts[k][1] - parts[k][0], k))
        a, b = parts[i]
        me = centre(a, b)
        options = []
        if i > 0:
            options.append((float(me @ centre(*parts[i - 1])), a))   # join the part before
        if i < len(parts) - 1:
            options.append((float(me @ centre(*parts[i + 1])), b))   # join the part after
        bounds.remove(max(options)[1])
    return bounds[1:-1]


def stretch_threshold(ssm, length, percentile):
    """Percentile of the mean diagonal similarity over every pair of non-overlapping stretches of `length` beats."""
    n = len(ssm) - length + 1
    if n <= length:
        return float("inf")
    sums = sum(ssm[k:k + n, k:k + n] for k in range(length)) / length
    i, j = np.triu_indices(n, k=length)
    return float(np.percentile(sums[i, j], percentile))


def returns(ssm, a, b, threshold, search_from=None):
    """Beat indices from search_from (default b) where the material of beats [a, b) comes back."""
    length = b - a
    n = len(ssm)
    scores = []
    for j in range(b if search_from is None else search_from, n - length + 1):
        scores.append((float(np.mean([ssm[a + k, j + k] for k in range(length)])), j))
    picked = []
    for score, j in sorted(scores, reverse=True):
        if score < threshold:
            break
        if all(abs(j - p) >= length for p in picked):
            picked.append(j)
    return sorted(picked)


def structure(raw, data):
    duration = raw["duration_seconds"]
    beats = [b for b in raw["beats_seconds"] if 0 < b < duration]
    edges = [0.0, *beats, duration]
    x = beat_chroma(raw["hpcp_frames"], raw["hpcp_hop_seconds"], edges)
    ssm = x @ x.T

    rep = repetition_matrix(embed(x, EMBED_BEATS), NEIGHBOUR_FRACTION)
    curve = novelty(rep, SMOOTH_BEATS)
    peaks, peak_threshold = boundaries(curve, MIN_SECTION_BEATS, PEAK_STD)
    peaks = merge_short(peaks, x, len(edges) - 1, MIN_PART_BEATS)
    repeat_threshold = stretch_threshold(ssm, RETURN_BEATS, REPEAT_PERCENTILE)

    harmony = data["music"]["harmony"]
    changes = harmony.get("chord_changes", [])
    starts = [0, *peaks]
    ends = [*peaks, len(edges) - 1]
    sections = []
    for a, b in zip(starts, ends):
        sec = {
            "start_seconds": round(edges[a], 3),
            "end_seconds": round(edges[b], 3),
            "label": "",
            # where this part's opening comes back, searched after the part ends
            "repeats": [round(edges[j], 3) for j in returns(ssm, a, a + RETURN_BEATS,
                                                            repeat_threshold, search_from=b)]
                       if b - a >= RETURN_BEATS else [],
        }
        rate = chord_changes_per_beat(changes, raw["beats_seconds"], edges[a], edges[b])
        if rate is not None:
            sec["chord_changes_per_beat"] = rate
        sections.append(sec)

    data["music"]["structure"] = {
        "available": True,
        "sections": sections,
        "settings": {
            "chroma": "Essentia HPCP frames averaged within each beat",
            "boundaries": "repetition-based novelty (Serra et al. 2014)",
            "embed_beats": EMBED_BEATS,
            "neighbour_fraction": NEIGHBOUR_FRACTION,
            "smooth_beats": SMOOTH_BEATS,
            "min_section_beats": MIN_SECTION_BEATS,
            "min_part_beats": MIN_PART_BEATS,
            "short_parts": "merged into the neighbour with the closest average chroma",
            "boundary_threshold": round(float(peak_threshold), 4),
            "repeat_threshold": round(repeat_threshold, 4),
            "return_beats": RETURN_BEATS,
        },
    }

    if harmony.get("available"):
        beat = 60.0 / raw["bpm"]
        # sample the chord half a beat before each section ends, not the one starting there
        harmony["key_reading"] = key_reading(
            harmony, duration, [s["end_seconds"] for s in sections], nudge=beat / 2)
    return data


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    raw_path, data_path = Path(sys.argv[1]), Path(sys.argv[2])
    raw = json.loads(raw_path.read_text())
    data = structure(raw, json.loads(data_path.read_text()))
    data_path.write_text(json.dumps(data, indent=2) + "\n")
    for s in data["music"]["structure"]["sections"]:
        back = ", ".join(f"{t:.1f}s" for t in s["repeats"]) or "-"
        print(f"  {s['start_seconds']:7.1f}s - {s['end_seconds']:7.1f}s   returns at: {back}")
    kr = data["music"]["harmony"].get("key_reading")
    if kr:
        print("key readings:", "; ".join(f"{r['key']} {r['mode']} ({', '.join(r['supported_by'])})"
                                         for r in kr["readings"]), "| ambiguous" if kr["ambiguous"] else "")
    print(f"updated {data_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
