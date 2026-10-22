# uMuse — round 1: local web app

## What this repo is

A **local web app** that shows one artist's real analysis results. Open it in a browser on
this computer, choose a track, click Analyze, and the page shows the reading. It is used on
screen in a 45-minute user session while the artist reads it aloud and explains what they
think each line means.

    python3 web/app.py        # then open http://127.0.0.1:8765

Flask backend (`web/app.py`), plain HTML/CSS/JS frontend (`web/static/`). No React, no accounts,
no database, no cloud hosting, no task queue. It listens on 127.0.0.1 only.

The only controls are the upload form and the Analyze button. While a track is being analysed
the form is disabled and shows "Analyzing your track…" — no percentages and no time estimates.
**The results themselves are not interactive**: no tabs, accordions, hover-to-reveal or links.

The earlier static page is kept as a reference: `template.html` + `scripts/build.py` still build
`out/<code>.html` from `data/<code>.json`, and `reference/p01.static-mockup.html` is the p01 page
shown with Moises chords. The results design is shared: `web/static/reading.js` and
`reading.css` draw both.

## The one rule that cannot be broken

**Never invent a number, a chord, a timestamp, a section boundary or a comparison.**

Every value on the page comes from the analysis JSON (`results/<code>.json` in the app,
`data/<code>.json` for the static build), which was produced by running the real analysis
pipeline on that artist's track. If a field is missing from the JSON, the page
says it is missing. It does not fill the gap with a plausible value.

The entire methodological point of this round is that the interface is fake and the content
is real. A single fabricated number makes the session worthless and I will not know which
finding was contaminated.

`scripts/check.py` runs on every analysis: the app (`scripts/pipeline.py`) and `scripts/build.py`
both refuse to show results that fail it, and the app shows the failed checks as an error
instead. Do not work around a failed check. Fix the data or mark the section unavailable.

## Scope of round one: the music only

Round one shows **harmony** and **structure**. These are the two analysis blocks committed to
in Sprint 1, and they are the reason the product exists. Comparisons against real songs sit
under both.

- **Harmony** — key, the chords as scale degrees placed on the timeline, the progression that repeats.
  In the app the chords come from **Chordino, run locally** (see "Where the chords come from").
- **Structure** — where the song's sections start and end, and where earlier material comes
  back. Sections are **not named**. No intro, verse or chorus. "This material returns at 0:48
  and 2:14" is the finding.
- **Tempo** — BPM and beat confidence only, because harmony timing depends on them.
- **Melody** — shown as unavailable, with the reason. Deferred to Sprint 2.

The mix (loudness, dynamics, brightness, width) is **deferred to Sprint 2** and does not appear
anywhere in the data or on the page. The same goes for syncopation and microtiming.

## Artists are confidential

Each artist is known by a code (`p01`, `p02`…) everywhere in this project. The link from code
to real name, and the audio itself, live only in the private vault (`~/uMuse-private`, see
`scripts/vault.py`), outside this folder.

- Add audio only through the app's upload or `scripts/intake.py`. Both use
  `intake.file_in_vault`, which assigns the code and copies the audio into the vault; the
  original recording is never touched. The app checks that the file decodes before it is filed.
- `raw/`, `data/` and the check accept a code and nothing else. No artist name, song title,
  original filename or lyric goes into them, including `notes`.
- The app and `build.py --with-names` are the only code that reads names from the vault
  (`vault.identity`). They put the real title on the page, because the artist is looking at their
  own song. That page identifies the artist: the app stays on 127.0.0.1, and built pages stay on
  this machine and are never committed, uploaded or published.
- Never open, read or print `participants.json`, and never copy the vault into this folder.
- `raw/`, `out/`, `results/`, `data/*.json`, `reference/` and audio files are git-ignored. Keep it that way.
- The app sends nothing anywhere: no Moises, no external service.

## Where the chords come from

**In the app: Chordino, run on this computer.** `scripts/pipeline.py` runs analyse → convert →
structure → billboard → harmonix → check. `analyse.py` gets the chords from Chordino (the NNLS-Chroma
Vamp plugin, built for this machine in `tools/vamp/`, see `PROVENANCE.txt`); Essentia still supplies
the key and its confidence, the tempo, the beats and the chroma for the parts of the song.
`chord_source.tool` is `"Chordino"` and covers the whole track. Chordino labels keep sevenths,
sixths and slash basses (`detail`, `bass_degree`, the same fields as Moises); it gives no strength,
so nothing is merged and there is no `chord_filter`. The page says "Chord estimates made on this
computer by Chordino; not checked by ear." Known limits stay on the record:
- On p01, 0:00–1:00, Chordino agreed with the Moises reading about 65% of the time (root and
  major/minor), against 28% for Essentia's Foundations detector. Neither is ground truth.
- Chordino's changes tend to land about a second after the change.
- `--chords foundations` / `--chords beats` still run Essentia's detectors (with strength and the
  short-chord merge, `tool: "Essentia"`) for comparison.

**Moises is reference only.** The p01 Moises reading (`reference/p01.moises.json`, applied by
`scripts/moises.py` into `data/p01.json`) was read by hand from the Moises chord chart on
2026-10-21 and covers 0:00–1:00. It is kept for comparison and for the static reference page.
Never present Moises chords as the app's own analysis, and never present the app's chords as
Moises's. If Moises is used again: the researcher uploads (the consent form must cover a cloud
service), extensions and slash-chord basses are kept (`detail`, `bass_degree`), Moises section
names never reach `data/`, and `covers_seconds` / `beyond_coverage` record what was read.

## Who reads it

One independent artist, working alone, who records and mixes their own music and has never
been taught to read a spectrum analyser. They have just been handed a reading of a song they
wrote. They are not a sound engineer and will not tolerate being spoken to as one.

## Design rules

**Plain language only.** No DSP or engineering terms on screen. Not chroma, not HPCP, not
self-similarity, not novelty curve, not key strength. Say what the finding means for the song.

**Chords in scale degrees**, never letter names. i–VI–III–VII, not Am–F–C–G. Show the key
separately. `scripts/convert.py` and `scripts/moises.py` do this. Letter-name chords exist only in
`raw/` and `reference/`, and never reach `data/` or the page. The tonic of the key is the only
letter name allowed.

Scale-degree convention. Upper case is a major chord and lower case is a minor chord. The
numeral is counted against the key's own scale (natural minor for minor keys), so in a minor
key the chord three semitones up is `III`, not `bIII`. Chords outside the scale take `b` or `#`:

| semitones above tonic | 0 | 1   | 2  | 3    | 4    | 5  | 6   | 7 | 8   | 9   | 10   | 11   |
|-----------------------|---|-----|----|------|------|----|-----|---|-----|-----|------|------|
| major key             | I | bII | II | bIII | III  | IV | #IV | V | bVI | VI  | bVII | VII  |
| minor key             | I | bII | II | III  | #III | IV | #IV | V | VI  | #VI | VII  | #VII |

`N` means the analysis found no clear chord there.

**Only key and tempo may be one value for the whole track.** This is a closed list. Every
other finding is reported at the point in the track where it happens, with a timestamp. That
includes chord-change rate, which is reported per section.

**Chord strength is never on screen.** Each Essentia chord change carries the detector's `strength`
(Moises chords have none).
It is used for two things only: deciding which short chords to merge, and hedging the wording
about weak chords. No figure, badge or bar for it. Two confidence scales are already enough.

**Merged chords are on the record.** For Essentia chords, `convert.py` absorbs chords that are both shorter than a
quarter beat and weaker than the track's median chord strength. The rule, the thresholds and the
count are in `music.harmony.chord_filter`, so "why isn't that chord showing?" has an answer.
It is not mentioned on the page unless the artist asks.

**Major or relative minor is said out loud.** A key and its relative minor use the same notes,
and the analysis often can't separate them. `music.harmony.key_reading` lists every reading the
key profiles (bgate, edma, temperley) and the chords themselves (most-heard chord, chord at most
section endings) support. When `ambiguous` is true, the page says so in plain words, e.g.
"This reads as C major. A minor uses the same notes and the analysis can't separate the two."
When the alternative is not the relative, say the analysis disagrees with itself, without
claiming the notes are the same. Next to the comparisons, say that they hold whichever reading
is right, because matching runs on the distance between chord roots, not on the key.
Never ask the artist what key the song is in. The researcher collects it before the session
as ground truth.

**Confidence is visible.** Where the JSON carries a confidence value, the page shows it, and
a low-confidence finding must read differently from a high-confidence one. Hedge the wording,
not just a badge. Two cautions:
- `key_confidence` is the analysis tool's key strength, a correlation score and not a
  probability. 0.7 does not mean "70% sure". Agree the wording thresholds in the copy step.
- `beat_confidence` has its own scale, stored next to it as `scale_max` (5.32 for Essentia's
  multi-feature tracker, whose documented bands are: under 1 very low, 1–1.5 low, 1.5–3.5 good,
  above 3.5 excellent). Never show it as a percentage.
- Chord timestamps can be off by up to about a second, because the chord detector smooths over a
  2-second window. Say "around 0:48", not "at 0:48.3".

**Findings are ordered**, most important first. Not a grid of equal-weight statistics.

**Unavailable is said out loud.** Every section, and every comparison dimension, carries
`available`. When it is `false`, the page shows the section with its `reason_if_unavailable`
in plain language. It is never dropped quietly and never filled.

**Comparisons run against two corpora.** McGill Billboard matches carry harmony and structure,
so they get an overall similarity. Harmonix has no chords, so its matches carry structure only,
with harmony marked unavailable, and no overall similarity.

**Comparisons never show a bare number.** Every similarity breaks into per-dimension scores,
and every dimension carries the evidence underneath it, with timestamps in both songs. The
evidence text is generated by the alignment script, never written by hand. `overall_similarity`
only exists when at least two dimensions are available. A score with no reason attached is
not shown.

**Say what the comparisons are against.** Name each corpus and its date range on the page
(`population_context`). McGill Billboard is US chart songs from 1958–1991. Harmonix is 912
Western pop songs, and the corpus gives no release dates, so the page says that rather than
guessing a range. Artists should see what they are being matched against.

## Never do these

- A score out of 100, a grade, a rating, or a verdict on whether the song is good
- Section names (intro, verse, chorus, bridge) in round one
- Anything implying the audio was or could be modified
- Genre labels or mood tags
- Invented competitor or reference tracks
- Placeholder/lorem content of any kind
- A progress bar, percentage or time estimate, or any simulated processing (a plain
  "Analyzing your track…" while real processing runs is fine)
- Interactive controls in the results, or any control that does nothing
- Anything from the mix
- A question to the artist, including what key the song is in
- A figure for chord strength

## Technical constraints

- App: Flask plus plain HTML, CSS and JavaScript. No frameworks, no npm, no build step, no
  external requests (no CDNs, fonts or analytics). One analysis at a time; uploads up to 200 MB
  in MP3, WAV, AIFF, FLAC or M4A.
- Static reference page: one self-contained `.html` file, data and the shared design inlined by
  `scripts/build.py`.
- Desktop first — the artist is on a laptop on a screen-share. It should not break at phone width.
- Readable at a glance over a compressed video call. Err large on type.
- One dark black-and-emerald theme, and only one: near-black and charcoal layers, dark-emerald
  fills, lines and primary button, a lighter emerald for emphasis text, ivory and warm-gray text, smoked-glass panels (blur over tonal gradients, with an
  opaque fallback). No theme toggle, so there is still one surface to review. All values are tokens
  in `web/static/reading.css`; check contrast against the rendered surfaces when changing them.
- Emerald marks emphasis and the one primary action. Uncertainty notes use sand, errors coral.
- The upload view has a hand-drawn feel, after the researcher's sketches: the Analyze button is an
  inline SVG (a block with streaks and flecks trailing left), and the form panel, the file well and
  Choose File get wobbly outlines drawn by `web/static/sketch.js` at their real size (seeded, so they
  never jitter; straight borders stay if the script doesn't run). Both are decoration only
  (aria-hidden); the controls underneath are the native button and file input. The results keep
  plain edges. Behind the whole app page, `web/static/notes.js` scatters the researcher's hand-drawn
  music symbols (notes, beams, clefs, accidentals, rests) as a fixed, seeded, sparse wallpaper in
  muted greens just above the page black, in the side margins only (never behind the form or the
  results; none when the margins are too narrow): texture only, aria-hidden, never carrying information.
  Major and minor chords, part boundaries and returns are told apart by shape and label
  (solid or dashed blocks, seams, diamonds), never by colour alone.
- Motion only on real controls and state changes, brief, and off under reduced motion. Result
  panels have no hover effects, so nothing in the results looks clickable.
- Helvetica Neue for every text, headings and chord numerals included (installed on macOS; falls
  back to Helvetica, then Arial), plus one bundled font: Ralmone (Natha Type) for the "uMuse"
  wordmark, the upload headline and the Analyze label only, served from
  `web/static/fonts/`. Its licence is personal use only (`fonts/RALMONE-LICENSE.txt`): any
  commercial use of uMuse needs a bought licence or another font. No CDNs or external assets.

## Repo layout

```
CLAUDE.md
template.html                 static reference page shell (data and shared-design markers)
data/EXAMPLE.schema.json      shape of the data; every value is a <placeholder>
raw/<code>.raw.json           Essentia output for the full track, chroma frames included
data/<code>.json              one per artist, produced by the scripts below
out/<code>.html               static reference page (round-one mockup)
scripts/intake.py             audio -> code name + private vault, then analyse.py
scripts/vault.py              where the vault is; the only code that reads real names
scripts/analyse.py            audio file -> raw/; Essentia (key, tempo, beats, chroma) + Chordino chords
tools/vamp/                   Chordino + vamp-simple-host built for arm64 (git-ignored; PROVENANCE.txt)
scripts/convert.py            raw/ -> harmony, tempo, melody; letter names -> degrees (read_label); Essentia-only merge; key reading
scripts/structure.py          raw/ chroma -> section boundaries and returns; adds section endings to the key reading
scripts/moises.py             reference/<code>.moises.json -> replaces the chords with Moises's, redoes loop and key reading
reference/<code>.moises.json  the Moises chord chart as read, letter names and all
scripts/billboard.py          data/<code>.json -> top McGill Billboard matches (harmony + structure) and a corpus statement
corpus/billboard/             McGill Billboard 2.0 index and SALAMI chord annotations (CC0; md5-checked against mirdata)
scripts/harmonix.py           data/<code>.json -> top Harmonix matches (structure only) and a corpus statement
corpus/harmonix/              Harmonix Set metadata, segments, beats (MIT; commit 64abeb5, sha256 in download/PROVENANCE.txt)
scripts/pipeline.py           one vault track -> the whole local analysis -> results/<code>.json, checked
scripts/check.py              the data check; pipeline.py and build.py run it every time
scripts/build.py              static reference page: checks the JSON, inlines it and the shared design
web/app.py                    the local web app (Flask): upload -> intake -> pipeline -> JSON
web/static/                   index.html, app.js/app.css (upload form), reading.js/reading.css (results design)
results/<code>.json           the app's analysis, Chordino chords (git-ignored)
COPY.md                       page copy with the JSON field behind every line
scripts/evaluate.py           scores parts, chords and key against a by-ear transcription (reference/<code>.truth.json)
```

Pipeline order (the app runs it in one request; `python3 scripts/pipeline.py <code>` runs it by hand):
upload or `intake.py` → `analyse.py` → `convert.py` → `structure.py` → `billboard.py` → `harmonix.py` →
`check.py`. The static reference adds `moises.py` after `structure.py` for p01 and finishes with `build.py`.