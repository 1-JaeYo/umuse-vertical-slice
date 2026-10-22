#!/usr/bin/env python3
"""Refuse analysis data that could put an invented value on the page.

    python scripts/check.py data/kene.json

build.py imports this and runs it before every build. Every problem is reported
with the path of the offending field. Exits non-zero if anything is wrong.

The check is strict on purpose: unknown keys are errors, so a deferred field
(mix, syncopation, a confidence with nothing real behind it) cannot slip back in.
"""
import json
import math
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"^<.*>$", re.DOTALL)
DEGREE = re.compile(r"^[b#]?(VII|VI|V|IV|III|II|I|vii|vi|v|iv|iii|ii|i)$|^N$")
CODE = re.compile(r"^p\d{2,}$")
SOURCES = {"McGill Billboard", "Harmonix"}
CHORD_TOOLS = {"Essentia", "Moises", "Chordino"}
FULL_LABEL_TOOLS = {"Moises", "Chordino"}  # labels with extensions and basses; no strength, nothing merged
# What a chord label adds beyond its root and major/minor quality, minus the letters.
DETAIL = re.compile(r"^(7|maj7|6|9|maj9|add9|11|13|sus2|sus4|7sus4|dim|dim7|7b5|aug)$")
BASS = re.compile(r"^[b#]?(VII|VI|V|IV|III|II|I)$")
SECTIONS = ["harmony", "structure", "groove", "melody"]
DIMENSIONS = {"harmony", "structure"}


class Checker:
    def __init__(self):
        self.errors = []
        self.duration = None

    def fail(self, path, msg):
        self.errors.append(f"{path}: {msg}")

    # ---- generic sweeps ----------------------------------------------------

    def sweep(self, node, path):
        """Placeholders and leftover schema comments, anywhere in the file."""
        if isinstance(node, dict):
            for k, v in node.items():
                kp = f"{path}.{k}" if path else k
                if k == "_comment":
                    self.fail(kp, "schema comment left in; this is still the example file")
                self.sweep(v, kp)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                self.sweep(v, f"{path}[{i}]")
        elif isinstance(node, str) and PLACEHOLDER.match(node.strip()):
            self.fail(path, f"schema placeholder {node!r} was never replaced")

    # ---- typed helpers ----------------------------------------------------

    def keys(self, obj, path, required, optional=()):
        if not isinstance(obj, dict):
            self.fail(path, f"expected an object, got {type(obj).__name__}")
            return False
        for k in required:
            if k not in obj:
                self.fail(f"{path}.{k}", "missing")
        for k in obj:
            if k not in required and k not in optional and k != "_comment":
                self.fail(f"{path}.{k}", "not in the round-one schema (deferred or unknown field)")
        return True

    def text(self, obj, key, path):
        v = obj.get(key)
        if key in obj and (not isinstance(v, str) or not v.strip()):
            self.fail(f"{path}.{key}", "must be non-empty text")

    def number(self, obj, key, path, lo=None, hi=None):
        if key not in obj:
            return None
        v = obj[key]
        return self.value(v, f"{path}.{key}", lo, hi)

    def value(self, v, path, lo=None, hi=None):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            self.fail(path, f"must be a number, got {v!r}")
            return None
        if lo is not None and v < lo:
            self.fail(path, f"{v} is below {lo}")
        if hi is not None and v > hi:
            self.fail(path, f"{v} is above {hi}")
        return v

    def time(self, v, path):
        return self.value(v, path, 0, self.duration)

    def times(self, obj, key, path, ordered=True):
        if key not in obj:
            return []
        seq = obj[key]
        if not isinstance(seq, list):
            self.fail(f"{path}.{key}", "must be a list")
            return []
        out = [self.time(t, f"{path}.{key}[{i}]") for i, t in enumerate(seq)]
        if ordered and all(t is not None for t in out) and out != sorted(out):
            self.fail(f"{path}.{key}", "timestamps are not in order")
        return out

    def availability(self, obj, path, required, optional=()):
        """Returns True if the block is available and its data keys should be checked."""
        if not isinstance(obj, dict):
            self.fail(path, "expected an object")
            return False
        avail = obj.get("available")
        if not isinstance(avail, bool):
            self.fail(f"{path}.available", "missing; every section says whether it is available")
            return False
        if not avail:
            self.keys(obj, path, ["available", "reason_if_unavailable"])
            self.text(obj, "reason_if_unavailable", path)
            return False
        return self.keys(obj, path, ["available", *required], optional)

    # ---- sections ----------------------------------------------------------

    def track(self, t):
        p = "track"
        # Identity lives only in the private vault; the data names the track by code.
        if not self.keys(t, p, ["code", "duration_seconds", "analysed_on", "pipeline"], ["notes"]):
            return
        if not CODE.match(str(t.get("code", ""))):
            self.fail(f"{p}.code", f"must be a participant code like p01, got {t.get('code')!r}")
        for k in ("pipeline", "notes"):
            self.text(t, k, p)
        self.duration = self.number(t, "duration_seconds", p, lo=1)
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(t.get("analysed_on", ""))):
            self.fail(f"{p}.analysed_on", "must be YYYY-MM-DD")

    def harmony(self, h):
        p = "music.harmony"
        if not self.availability(h, p, ["key", "mode", "key_confidence", "key_reading", "chord_changes", "chord_source"],
                                     ["loop", "chord_filter"]):
            return
        if not re.match(r"^[A-G][#b]?$", str(h.get("key", ""))):
            self.fail(f"{p}.key", f"must be a tonic letter, got {h.get('key')!r}")
        if h.get("mode") not in ("major", "minor"):
            self.fail(f"{p}.mode", "must be major or minor")
        self.number(h, "key_confidence", p, 0, 1)
        tool, (lo, hi) = self.chord_source(h.get("chord_source"), f"{p}.chord_source")
        # Essentia reports a strength per chord and its short chords are merged; Moises and Chordino do neither.
        if tool == "Essentia" and "chord_filter" not in h:
            self.fail(f"{p}.chord_filter", "missing; Essentia chords are always filtered and the filter is on the record")
        if tool in FULL_LABEL_TOOLS and "chord_filter" in h:
            self.fail(f"{p}.chord_filter", f"{tool} chords are not filtered; nothing was merged")
        changes = h.get("chord_changes")
        if not isinstance(changes, list) or not changes:
            self.fail(f"{p}.chord_changes", "must be a non-empty list")
            changes = []
        last = None
        for i, c in enumerate(changes):
            cp = f"{p}.chord_changes[{i}]"
            if tool in FULL_LABEL_TOOLS:
                if not self.keys(c, cp, ["at_seconds", "degree"], ["detail", "bass_degree"]):
                    continue
                if "detail" in c and not (isinstance(c["detail"], str) and DETAIL.match(c["detail"])):
                    self.fail(f"{cp}.detail", f"{c['detail']!r} is not a chord extension like 7 or maj7")
                if "bass_degree" in c and not (isinstance(c["bass_degree"], str) and BASS.match(c["bass_degree"])):
                    self.fail(f"{cp}.bass_degree", f"{c['bass_degree']!r} is not a scale step like I or bVII")
            else:
                if not self.keys(c, cp, ["at_seconds", "degree", "strength"]):
                    continue
                self.number(c, "strength", cp, 0, 1)
            self.degree(c.get("degree"), f"{cp}.degree")
            t = self.time(c.get("at_seconds"), f"{cp}.at_seconds")
            if t is not None and lo is not None and hi is not None and not lo <= t < hi:
                self.fail(f"{cp}.at_seconds", f"{t} is outside the stretch the chord source covers ({lo}-{hi})")
            if t is not None and last is not None and t <= last:
                self.fail(f"{cp}.at_seconds", "chord changes must move forward in time")
            last = t if t is not None else last
        if "key_reading" in h:
            self.key_reading(h["key_reading"], f"{p}.key_reading")
        if "chord_filter" in h:
            fp, cf = f"{p}.chord_filter", h["chord_filter"]
            if self.keys(cf, fp, ["rule", "min_duration_seconds", "max_strength", "segments_merged"]):
                self.text(cf, "rule", fp)
                self.number(cf, "min_duration_seconds", fp, lo=0)
                self.number(cf, "max_strength", fp, 0, 1)
                if not isinstance(cf.get("segments_merged"), int) or cf["segments_merged"] < 0:
                    self.fail(f"{fp}.segments_merged", "must be a whole number")
        if "loop" in h:
            lp = f"{p}.loop"
            loop = h["loop"]
            if self.keys(loop, lp, ["degrees", "occurs_at_seconds"]):
                degs = loop.get("degrees")
                if not isinstance(degs, list) or len(degs) < 2:
                    self.fail(f"{lp}.degrees", "a loop needs at least two chords")
                else:
                    for i, d in enumerate(degs):
                        self.degree(d, f"{lp}.degrees[{i}]")
                if len(self.times(loop, "occurs_at_seconds", lp)) < 2:
                    self.fail(f"{lp}.occurs_at_seconds", "a loop must occur at least twice")

    def chord_source(self, cs, path):
        """Which tool the chords came from and the stretch of the track they cover."""
        if not self.keys(cs, path, ["tool", "method", "covers_seconds"], ["observed_on", "beyond_coverage"]):
            return None, (None, None)
        tool = cs.get("tool")
        if tool not in CHORD_TOOLS:
            self.fail(f"{path}.tool", f"must be one of {sorted(CHORD_TOOLS)}")
        self.text(cs, "method", path)
        if tool == "Moises" and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(cs.get("observed_on", ""))):
            self.fail(f"{path}.observed_on", "Moises readings need the date they were read, YYYY-MM-DD")
        span = cs.get("covers_seconds")
        if not isinstance(span, list) or len(span) != 2:
            self.fail(f"{path}.covers_seconds", "must be [start, end]")
            return tool, (None, None)
        lo, hi = self.times(cs, "covers_seconds", path)
        if lo is not None and hi is not None and lo >= hi:
            self.fail(f"{path}.covers_seconds", "start must come before end")
        partial = hi is not None and self.duration is not None and hi < self.duration
        if partial and "beyond_coverage" not in cs:
            self.fail(f"{path}.beyond_coverage", "the chords stop before the track ends; say why, for the page")
        self.text(cs, "beyond_coverage", path)
        return tool, (lo, hi)

    def key_reading(self, kr, path):
        if not self.keys(kr, path, ["profiles", "relative", "readings", "ambiguous"],
                         ["most_heard", "section_endings"]):
            return
        for i, prof in enumerate(kr.get("profiles") or []):
            pp = f"{path}.profiles[{i}]"
            if self.keys(prof, pp, ["profile", "key", "mode", "strength"]):
                self.text(prof, "profile", pp)
                self.tonic(prof, pp)
                self.number(prof, "strength", pp, 0, 1)
        if not kr.get("profiles"):
            self.fail(f"{path}.profiles", "must list at least the primary key profile")
        if self.keys(kr.get("relative"), f"{path}.relative", ["key", "mode"]):
            self.tonic(kr["relative"], f"{path}.relative")
        readings = kr.get("readings")
        if not isinstance(readings, list) or not readings:
            self.fail(f"{path}.readings", "must be a non-empty list")
            readings = []
        for i, r in enumerate(readings):
            rp = f"{path}.readings[{i}]"
            if self.keys(r, rp, ["key", "mode", "relation", "supported_by"]):
                self.tonic(r, rp)
                if r.get("relation") not in ("primary", "relative", "other"):
                    self.fail(f"{rp}.relation", "must be primary, relative or other")
                if not isinstance(r.get("supported_by"), list) or not r["supported_by"]:
                    self.fail(f"{rp}.supported_by", "a reading needs at least one source")
        if kr.get("ambiguous") is not (len(readings) > 1):
            self.fail(f"{path}.ambiguous", "must be true exactly when more than one reading is listed")
        if "most_heard" in kr and self.keys(kr["most_heard"], f"{path}.most_heard", ["degree", "seconds"]):
            self.degree(kr["most_heard"].get("degree"), f"{path}.most_heard.degree")
            self.number(kr["most_heard"], "seconds", f"{path}.most_heard", lo=0)
        for i, e in enumerate(kr.get("section_endings") or []):
            ep = f"{path}.section_endings[{i}]"
            if self.keys(e, ep, ["at_seconds", "degree"]):
                self.time(e.get("at_seconds"), f"{ep}.at_seconds")
                self.degree(e.get("degree"), f"{ep}.degree")

    def tonic(self, obj, path):
        if not re.match(r"^[A-G][#b]?$", str(obj.get("key", ""))):
            self.fail(f"{path}.key", f"must be a tonic letter, got {obj.get('key')!r}")
        if obj.get("mode") not in ("major", "minor"):
            self.fail(f"{path}.mode", "must be major or minor")

    def degree(self, d, path):
        if not isinstance(d, str) or not DEGREE.match(d):
            self.fail(path, f"{d!r} is not a scale degree (letter-name chords must never reach data/)")

    def structure(self, s):
        p = "music.structure"
        if not self.availability(s, p, ["sections"], ["settings"]):
            return
        settings = s.get("settings", {})
        if not isinstance(settings, dict) or any(
                not isinstance(v, (str, int, float)) or isinstance(v, bool) for v in settings.values()):
            self.fail(f"{p}.settings", "must map setting names to numbers or text")
        sections = s.get("sections")
        if not isinstance(sections, list) or not sections:
            self.fail(f"{p}.sections", "must be a non-empty list")
            return
        prev_end = None
        for i, sec in enumerate(sections):
            sp = f"{p}.sections[{i}]"
            if not self.keys(sec, sp, ["start_seconds", "end_seconds", "repeats"],
                             ["label", "chord_changes_per_beat"]):
                continue
            if sec.get("label", "") != "":
                self.fail(f"{sp}.label", "sections are not named in round one; leave it empty")
            a = self.time(sec.get("start_seconds"), f"{sp}.start_seconds")
            b = self.time(sec.get("end_seconds"), f"{sp}.end_seconds")
            if a is not None and b is not None and a >= b:
                self.fail(sp, "start must come before end")
            if a is not None and prev_end is not None and a < prev_end:
                self.fail(f"{sp}.start_seconds", "overlaps the previous section")
            prev_end = b if b is not None else prev_end
            self.times(sec, "repeats", sp)
            self.number(sec, "chord_changes_per_beat", sp, lo=0)

    def groove(self, g):
        p = "music.groove"
        if not self.availability(g, p, ["bpm", "beat_confidence", "beats_seconds"]):
            return
        self.number(g, "bpm", p, lo=1)
        bc, bp = g.get("beat_confidence"), f"{p}.beat_confidence"
        if self.keys(bc, bp, ["value", "scale_max"]):
            top = self.number(bc, "scale_max", bp, lo=0)
            self.number(bc, "value", bp, 0, top)
        self.times(g, "beats_seconds", p)

    def melody(self, m):
        # Melody is deferred to Sprint 2; nothing about it may be shown yet.
        p = "music.melody"
        if isinstance(m, dict) and m.get("available") is True:
            self.fail(f"{p}.available", "melody is deferred to Sprint 2 and must be unavailable")
            return
        self.availability(m, p, [])

    def comparisons(self, c):
        p = "comparisons"
        if not self.availability(c, p, ["matches"]):
            return
        matches = c.get("matches")
        if not isinstance(matches, list) or not matches:
            self.fail(f"{p}.matches", "must be a non-empty list, or mark comparisons unavailable")
            return
        for i, m in enumerate(matches):
            mp = f"{p}.matches[{i}]"
            if not self.keys(m, mp, ["source", "title", "artist", "dimensions"],
                             ["year", "overall_similarity"]):
                continue
            if m.get("source") not in SOURCES:
                self.fail(f"{mp}.source", f"must be one of {sorted(SOURCES)}")
            self.text(m, "title", mp)
            self.text(m, "artist", mp)
            if "year" in m and (not isinstance(m["year"], int) or isinstance(m["year"], bool)):
                self.fail(f"{mp}.year", "must be a whole year, or omitted")
            dims = m.get("dimensions")
            if not self.keys(dims, f"{mp}.dimensions", sorted(DIMENSIONS)):
                continue
            live = sum(self.dimension(dims[d], f"{mp}.dimensions.{d}") for d in DIMENSIONS if d in dims)
            if "overall_similarity" in m:
                if live < 2:
                    self.fail(f"{mp}.overall_similarity",
                              f"only {live} dimension(s) available; an overall score needs at least two")
                self.number(m, "overall_similarity", mp, 0, 1)

    def dimension(self, d, path):
        if not self.availability(d, path, ["score", "evidence", "this_track_seconds", "reference_seconds"]):
            return False
        self.number(d, "score", path, 0, 1)
        self.text(d, "evidence", path)
        span = d.get("this_track_seconds")
        if not isinstance(span, list) or len(span) != 2:
            self.fail(f"{path}.this_track_seconds", "must be [start, end]")
        else:
            self.times(d, "this_track_seconds", path)
        ref = d.get("reference_seconds")
        if not isinstance(ref, list) or len(ref) != 2:
            self.fail(f"{path}.reference_seconds", "must be [start, end]")
        else:
            for j, t in enumerate(ref):
                self.value(t, f"{path}.reference_seconds[{j}]", lo=0)
        return True

    def population(self, pc):
        p = "population_context"
        if not self.availability(pc, p, ["statements"]):
            return
        stmts = pc.get("statements")
        if not isinstance(stmts, list) or not stmts:
            self.fail(f"{p}.statements", "must be a non-empty list")
            return
        for i, s in enumerate(stmts):
            sp = f"{p}.statements[{i}]"
            if self.keys(s, sp, ["statement", "basis"]):
                self.text(s, "statement", sp)
                self.text(s, "basis", sp)

    # ---- entry -------------------------------------------------------------

    def run(self, data):
        self.sweep(data, "")
        if not self.keys(data, "(top level)", ["track", "music", "comparisons", "population_context"]):
            return self.errors
        self.track(data["track"])
        music = data.get("music")
        if self.keys(music, "music", SECTIONS):
            for name in SECTIONS:
                if name in music:
                    getattr(self, name)(music[name])
        if "comparisons" in data:
            self.comparisons(data["comparisons"])
        if "population_context" in data:
            self.population(data["population_context"])
        return self.errors


def check(data):
    """Return a list of 'path: problem' strings. Empty means the data may be built."""
    return Checker().run(data)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    errors = check(json.loads(Path(sys.argv[1]).read_text()))
    for e in errors:
        print(e, file=sys.stderr)
    print(f"{len(errors)} problem(s)" if errors else "ok", file=sys.stderr if errors else sys.stdout)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
