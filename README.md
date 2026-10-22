# uMuse — vertical slice

A local web app that reads the harmony and structure of a song, for independent artists who write
and record their own music. Choose a track, click Analyze, and the page shows:

- **Harmony**: the key (and when the analysis can't tell it from its relative minor), the chords as
  scale degrees on a timeline, and the progression that repeats.
- **Structure**: where the parts of the song start and end, and where earlier material comes back.
  Parts are not named (no "verse" or "chorus").
- **Tempo**: BPM and how steady the beat reading is.
- **Comparisons** with real songs from two annotated collections: McGill Billboard (harmony and
  structure) and Harmonix (structure only). Every score comes with the evidence behind it,
  with timestamps in both songs.

Melody is shown as not available yet. Everything runs on this computer; nothing is sent to any
outside service.

Built for Minerva CP193 (capstone), round one of user testing. The rules the app follows, above
all **never invent a value**, are in [`CLAUDE.md`](CLAUDE.md). The page copy and the data field
behind every line are in [`COPY.md`](COPY.md).

## Requirements

- macOS on Apple silicon (the chord detector is compiled for arm64)
- Python 3 with `essentia`, `flask`, `numpy` and `scipy`
- Chordino, built locally into `tools/vamp/` (not in the repo; see below)

```sh
pip install essentia flask numpy scipy
```

### Building Chordino

The app's chords come from Chordino (the NNLS-Chroma Vamp plugin, GPL-2.0). It is built from
source and git-ignored. The app expects:

```
tools/vamp/vamp-simple-host
tools/vamp/plugins/nnls-chroma.dylib
```

```sh
brew install boost libsndfile

git clone https://github.com/vamp-plugins/vamp-plugin-sdk
cd vamp-plugin-sdk
make -f otherbuilds/Makefile.osx sdk host ARCHFLAGS="-arch arm64 -mmacosx-version-min=11.0"
cd ..

git clone https://github.com/c4dm/nnls-chroma
cd nnls-chroma
make -f Makefile.osx ARCHFLAGS="-arch arm64 -mmacosx-version-min=11.0" BOOST_ROOT=/opt/homebrew/include
```

Then copy `vamp-simple-host` into `tools/vamp/` and `nnls-chroma.dylib` into `tools/vamp/plugins/`.
The versions used were vamp-plugin-sdk `44c2487` and nnls-chroma `4c5f214`.

## Running the app

```sh
python3 web/app.py
```

Open http://127.0.0.1:8765. The app listens on this computer only. It accepts MP3, WAV, AIFF,
FLAC and M4A files up to 200 MB, and runs one analysis at a time.

## Privacy

Artists are known only by a code (`p01`, `p02`, …). Uploaded audio is copied into a private vault
outside the project, `~/uMuse-private` (or `$UMUSE_VAULT`), which is the only place a code is
linked to a name. The original file is never changed.

The audio, the vault and every analysis output (`raw/`, `results/`, `data/*.json`, `out/`,
`reference/`) are git-ignored. Pages the app shows carry the artist's real song title, so they stay
on this machine.

## How the analysis works

The app runs one pipeline per track (`scripts/pipeline.py`):

| Step | Script | What it does |
|---|---|---|
| 1 | `intake.py` | Assigns the code and files the audio in the vault |
| 2 | `analyse.py` | Essentia: key, tempo, beats, chroma. Chordino: chords |
| 3 | `convert.py` | Chords to scale degrees; key reading; repeating progression |
| 4 | `structure.py` | Part boundaries and returns from chroma self-similarity |
| 5 | `billboard.py` | Closest McGill Billboard songs by harmony and structure |
| 6 | `harmonix.py` | Closest Harmonix songs by structure |
| 7 | `check.py` | Refuses to show results that break the data rules |

Results land in `results/<code>.json`. To run the pipeline by hand on a track already in the vault:

```sh
python3 scripts/pipeline.py p01
```

`scripts/evaluate.py` scores the analysis against a by-ear transcription
(`reference/<code>.truth.json`): part boundaries, chord agreement over time, and key.

### Static reference page

The round-one mockup is kept alongside the app. `scripts/build.py` builds `out/<code>.html`, a
single self-contained page, from `data/<code>.json`, using `template.html` and the same results
design as the app (`web/static/reading.js` and `reading.css`).

## Project layout

```
web/app.py            Flask app: upload -> intake -> pipeline -> JSON
web/static/           upload view (index.html, app.js, app.css, sketch.js, notes.js)
                      and results design (reading.js, reading.css); fonts/
scripts/              the analysis pipeline, the data check, evaluation, static build
corpus/billboard/     McGill Billboard 2.0 index and chord annotations
corpus/harmonix/      Harmonix Set metadata, segments and beats
data/                 EXAMPLE.schema.json: the shape of the analysis data
template.html         static reference page shell
```

## Licences and sources

- **McGill Billboard 2.0** annotations: CC0.
- **Harmonix Set**: MIT (commit `64abeb5`; checksums in `corpus/harmonix/download/PROVENANCE.txt`).
- **Chordino / NNLS-Chroma**: GPL-2.0. Built locally and not distributed in this repo.
- **Ralmone** (Natha Type), used for the wordmark, headline and Analyze label: personal-use
  licence (`web/static/fonts/RALMONE-LICENSE.txt`). Any commercial use of uMuse needs a bought
  licence or a different font.
