#!/usr/bin/env python3
"""Run the Foundations Essentia analysis on a full local audio file.

    python scripts/analyse.py ~/uMuse-private/audio/p01.mp3 raw/p01.raw.json --code p01
    python scripts/analyse.py ~/uMuse-private/audio/p01.mp3 raw/p01.beats.raw.json --code p01 --chords beats

Normally run for you by scripts/intake.py, which assigns the code. The output names
the track only by its code; the real artist and title never enter it.

Makes the same extractor calls, with the same settings, as
u-muse-foundations/backend/app/services/analysis_service.py (commit 6e7cf7d):
MonoLoader at 44.1 kHz, RhythmExtractor2013(method="multifeature"), KeyExtractor(),
TonalExtractor(). Differences, all deliberate:

- It reads a local file instead of a 30-second Deezer preview.
- It keeps what Foundations throws away: the time and strength of every chord, and
  the chroma (HPCP) frames that Foundations averages into one vector. The structure
  step needs the frames.
- It also runs KeyExtractor with the edma and temperley profiles, for comparison
  with the default (bgate). The default stays the primary reading.
- Chords come from Chordino by default (`--chords chordino`): the NNLS-Chroma Vamp plugin,
  built for this machine in tools/vamp/. It hears sevenths, sixths and slash chords, which
  Essentia's major/minor-only detectors can't. On p01 it agreed with the Moises reading of
  0:00-1:00 about 65% of the time, against 28% for Foundations' detector.
- `--chords foundations` keeps Foundations' own detector (ChordsDetection, which smooths
  over a 2-second window and can erase short passing chords); `--chords beats` uses
  ChordsDetectionBeats, one chord per beat from the same chroma frames (experimental in
  Essentia). Key, tempo, beats and chroma always come from Essentia.

Loudness, energy, spectral centroid and MFCC are not computed; the mix is Sprint 2.

The output is the raw input that scripts/convert.py reads.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import essentia
import essentia.standard as es

SAMPLE_RATE = 44100
# TonalExtractor defaults, which Foundations uses unchanged. One chord label and one
# chroma frame per hop, so frame i starts at i * TONAL_HOP / SAMPLE_RATE seconds.
TONAL_FRAME = 4096
TONAL_HOP = 2048
# Documented range of BeatTrackerMultiFeature's confidence (Zapata et al., ISMIR 2012).
BEAT_CONFIDENCE_SCALE_MAX = 5.32
PRIMARY_KEY_PROFILE = "bgate"  # KeyExtractor's default, as used by Foundations
OTHER_KEY_PROFILES = ["edma", "temperley"]
CHORD_DETECTORS = {
    "chordino": "Chordino (NNLS-Chroma Vamp plugin, Mauch & Dixon 2010), run by uMuse",
    "foundations": "ChordsDetection via TonalExtractor (2 s smoothing window), as in Foundations",
    "beats": "ChordsDetectionBeats, one chord per beat from TonalExtractor chroma (experimental in Essentia)",
}
DEFAULT_DETECTOR = "chordino"
# Built from source for this machine; see tools/vamp/PROVENANCE.txt.
VAMP_DIR = Path(os.environ.get("UMUSE_VAMP_DIR", Path(__file__).resolve().parent.parent / "tools" / "vamp"))
CHORDINO = "nnls-chroma:chordino:simplechord"


def chords_per_frame(chords, strength, hop_seconds):
    return [{"at_seconds": round(i * hop_seconds, 3), "chord": c, "strength": round(float(s), 4)}
            for i, (c, s) in enumerate(zip(chords, strength))]


def chords_per_beat(hpcp, beats, duration):
    ticks = [0.0] + [b for b in beats if 0 < b < duration] + [duration]
    chords, strength = es.ChordsDetectionBeats(hopSize=TONAL_HOP, sampleRate=SAMPLE_RATE)(
        hpcp, essentia.array(ticks))
    return [{"at_seconds": round(ticks[i], 3), "chord": c, "strength": round(float(s), 4)}
            for i, (c, s) in enumerate(zip(chords, strength))]


def chords_by_chordino(audio):
    """Chordino's chord changes for decoded mono audio at SAMPLE_RATE: [{at_seconds, chord}].

    Chordino reports a change only when the chord changes, with its own smoothing, and
    gives no strength. Its labels keep sevenths, sixths and slash basses (e.g. "Em7",
    "C/E"); convert.read_label turns them into degrees without dropping any of that.
    """
    host = VAMP_DIR / "vamp-simple-host"
    plugin = "nnls-chroma.dylib" if sys.platform == "darwin" else "nnls-chroma.so"
    if not host.exists() or not (VAMP_DIR / "plugins" / plugin).exists():
        raise RuntimeError(f"Chordino is not built; see {VAMP_DIR / 'PROVENANCE.txt'}")
    with tempfile.TemporaryDirectory() as tmp:
        wav, out = Path(tmp) / "audio.wav", Path(tmp) / "chords.txt"
        es.MonoWriter(filename=str(wav), sampleRate=SAMPLE_RATE, format="wav")(audio)
        run = subprocess.run([str(host), CHORDINO, str(wav), "-o", str(out)], capture_output=True, text=True,
                             env={**os.environ, "VAMP_PATH": str(VAMP_DIR / "plugins")}, timeout=600)
        if run.returncode != 0 or not out.exists():
            raise RuntimeError(f"Chordino failed: {(run.stderr or run.stdout).strip()[-300:]}")
        lines = out.read_text().splitlines()
    duration = len(audio) / SAMPLE_RATE
    chords = []
    for line in lines:
        t, _, label = line.partition(":")
        # Chordino's last window runs past the end of the file and closes with an "N" there;
        # a change at or after the last sample describes no audio, so it is left out.
        if label.strip() and float(t) < duration:
            chords.append({"at_seconds": round(float(t), 3), "chord": label.strip()})
    if not chords:
        raise RuntimeError("Chordino returned no chords")
    return chords


def analyse(path, code, detector=DEFAULT_DETECTOR, notes=None):
    audio = es.MonoLoader(filename=str(path), sampleRate=SAMPLE_RATE)()
    if len(audio) == 0:
        raise ValueError(f"{path} decoded to no audio")
    duration = len(audio) / SAMPLE_RATE

    bpm, beats, beat_confidence, _estimates, _intervals = es.RhythmExtractor2013(method="multifeature")(audio)
    profiles = []
    for name in [PRIMARY_KEY_PROFILE, *OTHER_KEY_PROFILES]:
        key, scale, strength = es.KeyExtractor(profileType=name)(audio)
        profiles.append({"profile": name, "key": key, "scale": scale, "strength": round(float(strength), 4)})
    tonal = es.TonalExtractor(frameSize=TONAL_FRAME, hopSize=TONAL_HOP)(audio)
    chords, chord_strength, hpcp = tonal[4], tonal[6], tonal[7]
    if not len(chords) == len(chord_strength) == len(hpcp):
        raise ValueError(f"expected one chord per chroma frame, got {len(chords)}, {len(chord_strength)}, {len(hpcp)}")

    hop_seconds = TONAL_HOP / SAMPLE_RATE
    beats = [float(b) for b in beats]
    if detector == "chordino":
        timed_chords = chords_by_chordino(audio)
    elif detector == "beats":
        timed_chords = chords_per_beat(hpcp, beats, duration)
    else:
        timed_chords = chords_per_frame(chords, chord_strength, hop_seconds)

    primary = profiles[0]
    raw = {
        "code": code,
        "duration_seconds": round(duration, 3),
        "analysed_on": datetime.date.today().isoformat(),
        "pipeline": (f"Essentia {essentia.__version__}; Foundations extractor calls (6e7cf7d) on the full "
                     f"local file; chords: {CHORD_DETECTORS[detector]}"),
        "key": primary["key"],
        "scale": primary["scale"],
        "key_strength": primary["strength"],
        "key_profiles": profiles,
        "bpm": float(bpm),
        "beats_seconds": beats,
        "beat_confidence": float(beat_confidence),
        "beat_confidence_scale_max": BEAT_CONFIDENCE_SCALE_MAX,
        "chord_detector": detector,
        "chords": timed_chords,
        "hpcp_hop_seconds": hop_seconds,
        "hpcp_frames": [[round(float(v), 4) for v in frame] for frame in hpcp],
    }
    if notes:
        raw["notes"] = notes
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio")
    parser.add_argument("out")
    parser.add_argument("--code", required=True, help="participant code, e.g. p01")
    parser.add_argument("--chords", choices=sorted(CHORD_DETECTORS), default=DEFAULT_DETECTOR)
    parser.add_argument("--notes", help="anything unusual about this run")
    args = parser.parse_args()

    raw = analyse(Path(args.audio), args.code, args.chords, args.notes)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(raw) + "\n")
    print(f"wrote {out}: {raw['duration_seconds']}s, {len(raw['chords'])} chord slots ({args.chords})")
    for p in raw["key_profiles"]:
        print(f"  key profile {p['profile']:9s} {p['key']} {p['scale']} (strength {p['strength']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
