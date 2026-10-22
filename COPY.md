# Round-one page: data report, reading order, copy

The page is drawn by `web/static/reading.js`, which both the app and the static reference use.
Change the wording here first, then in `reading.js`.

**Current as of 2026-10-21.** The values come from the app's analysis of p01, `results/p01.json`
(Chordino chords, 7 parts, 16-move chord scoring). Rerun the pipeline and update sections 1 and 4
whenever the scripts change.

The static reference (`data/p01.json`, `reference/p01.static-mockup.html`) uses the same copy. It
differs only where its Moises chords differ, listed at the end of section 4.

## 1. What is in results/p01.json

| Block | State | Confidence |
|---|---|---|
| Key | G major from all three key tests. Flagged ambiguous with E minor: 4 of the 7 parts end on vi, including the end of the song. | Key fit 0.85, a fit score, not a probability. The E-minor flag rests on a slim majority (see section 5). |
| Chords | 96 Chordino changes over the whole track (0:00–3:11). Kept as degrees plus what each label adds: 29 sixths, 16 sevenths, 15 maj7s, 2 slash chords. | Chordino gives no confidence. Not checked by ear. Changes can land about a second late. On 0:00–1:00 it agrees with the Moises reading 64% of the time. |
| Loop | vi → V → I → IV, starting 7 times. | Follows from the chords. |
| Structure | 7 unnamed parts, the shortest about 15 s. The openings of 3 parts come back later, 8 returns in all. | No confidence value exists. In the first minute it finds 1 of the 3 part starts Moises shows (see section 5). |
| Tempo | 112 bpm. | Beat confidence 2.29 on 0–5.32, the "good" band. |
| Melody | Unavailable (Sprint 2). Shown with its reason. | n/a |
| Billboard | 5 matches with chords, shape and overall (0.60–0.76). | Only the top match, *Hungry Eyes*, holds across chord windows of 8–24 moves; the others shift. |
| Harmonix | 5 matches, shape only, all 0.71. Chords unavailable, with the reason. No overall. | These are the only five songs at 0.71; the next score is 0.57. |
| Population | 1 Billboard statement (the loop's moves), 1 Harmonix statement (number of parts). | Each names its basis. |

Missing on purpose: section names, anything from the mix, chord strength, any chord confidence (none exists).

## 2. Reading order

Argued from what an artist writing alone wants to know about their own song: first "what is my song made of", then "how is it laid out", then "what is it like".

1. **Header.** Title, artist, length, one line on what the page is and that it says what it couldn't work out.
2. **The chords that keep coming back.** The loop and where it starts, the key and why it might be read differently, then every chord change on a timeline.
3. **The shape of the song.** A map of the parts, where each part's opening comes back, and how often the chords change in each part.
4. **Tempo.** One line plus beat confidence.
5. **Melody: not analysed yet.** Kept above the comparisons, so the "what the system couldn't do" moment comes while the artist is still reading about their own song.
6. **Songs that line up with yours.** Billboard (chords and shape), then Harmonix (shape only), each opened by what the collection is.
7. **How this was made.** Sources and dates.

In the app, the upload form sits above all of this. The results themselves have nothing to click.

## 3. Copy, line by line

`{...}` is filled from the field named in the right column. Lines marked *static* are fixed text.
Times from chords and returns read "around m:ss".

### Header
| Line | Source |
|---|---|
| {IDENTITY.title}, or "Track {code}" without names | vault title / track.code |
| by {IDENTITY.artist} (left out when no artist was given) | vault artist |
| {m:ss} long · analysed {date} | track.duration_seconds, track.analysed_on |
| This is a reading of your song's chords and shape, made by software. Each finding says where in the song it happens. Where the software couldn't work something out, this page says so. | *static* |

### The chords that keep coming back
| Line | Source |
|---|---|
| Your song keeps coming back to this run of chords: **vi → V → I → IV**. | harmony.loop.degrees |
| Across the song, this run starts 7 times: around 0:00, 0:08, … *(more than 8 starts are cut to the first 8 plus "N more times after that"; with partial chords: "In the stretch we could read (a–b)")* | loop.occurs_at_seconds, chord_source.covers_seconds |
| **Key: G major** | harmony.key, mode |
| The chord numbers count from G: I is the chord built on G, IV the one built four notes up, and so on. Capitals are major chords, small letters minor. | harmony.key + *static* |
| This reads as G major: all three key tests point there. But E minor uses the same notes, and 4 of the 7 parts end on its home chord (vi), including the end of the song. The analysis can't separate the two. *(when not ambiguous: "Three separate key tests all read G major.")* | key_reading.readings[].supported_by, section_endings, track.duration_seconds |
| How clearly the notes point to G major: **0.85** on a 0–1 scale. They point to it clearly. This is a fit score, not a percentage chance. | harmony.key_confidence; wording thresholds in section 5 |
| The chord heard longest in the song is **IV**, about 58 seconds in all. | key_reading.most_heard |
| Every chord change, 0:00–3:11 *(timeline: one block per chord, in rows of 15 s; a chord carried over from the row before is shown in brackets; marks where the run starts)* | chord_changes[], loop.occurs_at_seconds |
| Each block is one chord, as long as it lasts. Solid blocks are major chords and dashed blocks minor, as the numerals say: capitals major, small letters minor. A label too long for its block sits just below it, joined by a short line. Marks above a row show where the repeating run starts. *(timeline legend)* | *static* |
| One line per kind of chord that appears, e.g. "vi7 is the vi chord with a seventh added." "II/III means the II chord with the III note in the bass." "N marks a stretch where the software heard no clear chord." | chord_changes[].detail, .bass_degree, degree "N" |
| Chord estimates made on this computer by Chordino; not checked by ear. A chord change can show up about a second after it happens. *(Moises: "Chord estimates from Moises; not independently verified. Times are approximate." plus its coverage note)* | chord_source.tool, .beyond_coverage |

### The shape of the song
| Line | Source |
|---|---|
| The software split your song into **7 parts** by listening for where the sound repeats and where it changes. It doesn't name them. | structure.sections |
| Map with numbered parts, a list of each part's times, dashed marks with a diamond under the map where openings come back, a line above the map marking the stretch with chords. Legend: "Numbered blocks are the parts in order, with their times listed above. Dashed marks with a diamond, under the map, show where earlier material comes back. The line above the map marks the stretch whose chords were read." | sections[].start/end_seconds, .repeats, chord_source.covers_seconds |
| The opening of the part starting around 0:34 comes back around 1:17, around 1:43, around 1:51, around 2:19 and around 2:28. *(one line per part with returns)* | sections[].start_seconds, .repeats |
| How often the chords change: about once every 3.7 beats in the part from 0:00 to 0:34 … *(a list when more than two parts)* | 1 ÷ sections[].chord_changes_per_beat |
| Where one part ends and the next begins is the software's estimate. *(adds "N of the M parts are shorter than 10 seconds…" only when there are any; p01 has none)* | sections[] lengths; 10 s is a template constant |

### Tempo
| Line | Source |
|---|---|
| **About 112 beats per minute.** | groove.bpm |
| How easy the beat was for the software to follow: 2.3 on its 0–5.3 scale. That is in the "good" band; above 3.5 counts as excellent, below 1 as very low. | groove.beat_confidence; band edges are a template constant (section 5) |

### Melody
| Line | Source |
|---|---|
| **Melody: not analysed yet** / Melody analysis is scheduled for Sprint 2 and was not run on this track. | melody.reason_if_unavailable |

### Songs that line up with yours
| Line | Source |
|---|---|
| We compared your song with two collections of songs that people annotated by hand. These are likenesses in how the chords move and how long the parts are. They are not about sound, lyrics or quality. | *static* |
| The chord comparison follows how far each chord moves to the next, so it holds whichever key your song is heard in. | *static* (CLAUDE.md rule) |
| **US chart songs, 1958–1991 (McGill Billboard)**, its basis, its statement | population_context.statements[0] |
| *per match:* title, artist, charted {year}; Overall {x} on a 0–1 scale: the average of chords and shape. | matches[].title, artist, year, overall_similarity |
| Chords {x}: In the best-matching stretch of 16 chord moves in your song, 13 line up, in order, with *Hungry Eyes*: around 1:25–1:54 in yours and 2:06–2:45 in theirs. … In yours that stretch runs vi → II → V → … | dimensions.harmony.score, evidence (billboard.py) |
| Shape {x}: 5 of the 7 parts of your song line up, in order, with parts of *Hungry Eyes* that are within 1 bar of the same length: … Lengths in bars, yours: …; theirs: … | dimensions.structure.score, evidence |
| **Western pop songs (Harmonix Set)**, its basis, its statement; per match: Chords: not available. The Harmonix Set has no chord annotations, so harmony can't be compared. Shape {x}: … | statements[1], matches[] (harmonix.py) |

### How this was made
| Line | Source |
|---|---|
| Chords by Chordino; key, tempo and parts from the uMuse analysis. All run on this computer, 2026-10-21. *(Moises: "Chords read from Moises on {date}. Key, tempo and parts from the uMuse analysis, run {date}.")* | chord_source.tool, observed_on, track.analysed_on |

## 4. Every number on the p01 page (app), with its source

| On the page | JSON path (value) |
|---|---|
| 3:11 long | track.duration_seconds (190.746) |
| analysed 2026-10-21 | track.analysed_on |
| vi → V → I → IV | harmony.loop.degrees |
| starts 7 times: around 0:00, 0:08, 0:43, 1:00, 1:43, 2:17, 2:25 | loop.occurs_at_seconds (0.232, 8.173, 42.725, 59.768, 102.586, 137.323, 145.264) |
| Key: G major | harmony.key, mode |
| all three key tests | count of "… key profile" in readings[0].supported_by (3) |
| E minor | key_reading.readings[1] (relation "relative") |
| 4 of the 7 parts end on vi, including the end of the song | key_reading.section_endings (vi at 34.296, 156.444, 172.048, 190.746 of 7) |
| 0.85 | harmony.key_confidence (0.8505) |
| IV, about 58 seconds | key_reading.most_heard (IV, 57.587) |
| Every chord change, 0:00–3:11; every block | chord_source.covers_seconds ([0, 190.746]); chord_changes[] (96) |
| 7 parts; parts list 0:00–0:34, 0:34–1:14, 1:14–1:50, 1:50–2:09, 2:09–2:36, 2:36–2:52, 2:52–3:11 | structure.sections[].start/end_seconds |
| 0:34 → 1:17, 1:43, 1:51, 2:19, 2:28 | sections[1].repeats (77.16, 102.864, 111.433, 139.297, 147.865) |
| 1:14 → 1:50, 2:23 | sections[2].repeats (110.364, 143.058) |
| 1:50 → 2:24 | sections[3].repeats (144.126) |
| once every 3.7 / 4.0 / 3.7 / 2.9 / 3.5 / 3.6 / 5.8 beats | 1 ÷ sections[0–6].chord_changes_per_beat (0.27, 0.253, 0.273, 0.343, 0.288, 0.276, 0.171) |
| About 112 beats per minute | groove.bpm (111.97) |
| 2.3 on its 0–5.3 scale; "good" band | groove.beat_confidence.value (2.286), .scale_max (5.32); band edges 1 / 1.5 / 3.5 are a template constant |
| 1958–1991; 742 songs; 24 of 742, 3% | population_context.statements[0] |
| Hungry Eyes, Eric Carmen, 1988: overall 0.76, chords 0.81, shape 0.71 | comparisons.matches[0] (0.763, 0.812, 0.714) |
| Back Home Again, John Denver, 1974: 0.69, 0.81, 0.57 | matches[1] (0.692, 0.812, 0.571) |
| Surfin' Safari, The Beach Boys, 1962: 0.63, 0.69, 0.57 | matches[2] (0.629, 0.688, 0.571) |
| Sweet Soul Music, Arthur Conley, 1967: 0.63, 0.69, 0.57 | matches[3] (0.629, 0.688, 0.571) |
| Two Hearts, Phil Collins, 1989: 0.60, 0.62, 0.57 | matches[4] (0.598, 0.625, 0.571) |
| Harmonix: Conceited (Remy Ma), Super Freak (Rick James), Cinema (Benny Benassi), Good Time (Carly Rae Jepsen with Owl City), Stronger (Kanye West), shape 0.71 each | matches[5–9].dimensions.structure.score (0.714) |
| Every number inside an evidence sentence (moves, parts, bars, times) | matches[].dimensions.*.evidence, generated by billboard.py / harmonix.py |
| 912 songs; 7 parts; 8 and 12; 10 | population_context.statements[1] |
| Chordino … 2026-10-21 | chord_source.tool, track.analysed_on |

Template constants, not findings: rows of 15 s (ROW_SECONDS), the 10-second short-part note, the beat-confidence band edges, and the key-fit wording thresholds.

**Static reference (data/p01.json) differences:** chords from Moises, 0:00–1:00 only, with the coverage note. Key G major, not ambiguous: only one part ending falls inside the minute, below the minimum of 3. Its Billboard matches are Hungry Eyes 0.67, Deeper Shade Of Soul 0.63, Count On Me 0.62, Surfin' Safari 0.60 and Promises 0.59. Parts, tempo and Harmonix are the same as the app's.

## 5. Open decisions and what has been checked

**Settings and how sure we are of them**
- **Minimum part length: 4 bars (structure.py MIN_PART_BEATS = 16).** Only 4.0% of hand-annotated Harmonix parts and 5.6% of Billboard parts are shorter. On p01, any minimum from 16 to 24 beats gives identical parts, returns and matches; 8 or 12 change all of them.
- **Chord window: 16 moves (billboard.py HARMONY_WINDOW_MOVES).** This is a choice of what to compare, so no transcription can confirm it. *Hungry Eyes* is the top match at 8, 12, 16 and 24 moves, and only drops at 32. The songs below it change with the window.
- **Key flag needs at least 3 part endings (convert.py MIN_SECTION_ENDINGS).** On p01 the E-minor flag rests on 4 of 7 endings. At 12-beat parts it would be 5 of 10 and the flag would go. Treat it as borderline. The researcher's pre-session key from the artist settles it.

**Parts vs Moises in the first minute.** The analysis finds the part start at 0:34 that Moises shows, but not the ones at 0:17 and 0:51. The novelty curve has only a weak peak at 0:17 (0.50 against a threshold of 0.58) and none at 0:51, and its strongest early peaks are at 0:03 and 0:42. The song repeats one chord loop, so its parts differ in arrangement (voice, drums, texture) more than in chords, and the chord-based features can't hear that. Lowering the threshold would add wrong boundaries too. A real fix would add sound-colour (timbre) features to the boundary search: a scope decision, because the mix is deferred.

**Checking against a human transcription.** `scripts/evaluate.py` scores the parts (precision, recall and F1, within 1 bar), the chords (time agreement on root and major/minor) and the key against a by-ear transcription. `--sweep` re-scores other minimum part lengths:

    python scripts/evaluate.py --template p01 > reference/p01.truth.json   # fill in by ear
    python scripts/evaluate.py reference/p01.truth.json --sweep

Mechanics are verified with the Moises reading as a stand-in, not as truth: Moises against itself scores 100% on chords, and Chordino 64%. On 0:00–1:00 parts it gives F1 0.50 at 16 beats against 0.40 at 8. No human transcription of p01 exists yet.

**Wording still to confirm**
- Key-fit thresholds: 0.75 and above "clearly"; 0.5–0.75 "with some notes from outside it"; below 0.5 "only loosely…".
- Beat-confidence band edges come from the tracker's documentation, not from the JSON.
- "Chord moves" is the plainest wording found for distances between chord roots.
