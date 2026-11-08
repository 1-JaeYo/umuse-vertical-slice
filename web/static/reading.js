// Renders one analysis (DATA) into `page`. Shared by the static build (template.html,
// inlined by scripts/build.py) and the local web app (web/static/index.html).
// IDENTITY is {artist, title} or null.
function renderReading(DATA, IDENTITY, page) {
  // Every value below comes from DATA (or IDENTITY). Text marked "static" is fixed copy
  // from COPY.md. Nothing here is interactive: no links, buttons, hover text or titles.
  const ROW_SECONDS = 15;
  // Documented bands of Essentia's multi-feature beat tracker (Zapata et al. 2012), as in CLAUDE.md.
  const BEAT_BANDS = [[1, "very low"], [1.5, "low"], [3.5, "good"], [Infinity, "excellent"]];
  // Proposed key-fit wording thresholds, pending the copy review (COPY.md).
  const KEY_FIT = [[0.75, "They point to it clearly."],
                   [0.5, "They point to it, with some notes from outside it."],
                   [-Infinity, "They point to it only loosely, so treat the key with caution."]];

  const music = DATA.music, harmony = music.harmony, structure = music.structure, groove = music.groove;

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "style") Object.assign(n.style, v); else n.setAttribute(k, v);
    }
    for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false)
      n.append(typeof k === "string" ? document.createTextNode(k) : k);
    return n;
  }
  const clock = s => { const r = Math.round(s); return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`; };
  const around = s => `around ${clock(s)}`;
  const list = xs => xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
  const fixed = (x, d) => Number(x).toFixed(d);
  const chordLabel = c => c.degree + (c.detail || "") + (c.bass_degree ? `/${c.bass_degree}` : "");
  const isMinor = d => /^[b#]?[iv]+$/.test(d);

  // ---- timeline layout ------------------------------------------------------------------
  // Runs after the timeline is in the page, and again when its width changes. Nothing here
  // changes a time or a label: it only decides where a label that doesn't fit is drawn.
  const layouts = [];
  const measure = (() => {
    const ctx = document.createElement("canvas").getContext("2d");
    return (text, node) => { ctx.font = getComputedStyle(node).font; return ctx.measureText(text).width; };
  })();
  function placeInLanes(items, gap) {
    // items: [{left, width}] in order; returns the lane index for each, first lane that has room
    const ends = [];
    return items.map(it => {
      let lane = ends.findIndex(e => it.left >= e + gap);
      if (lane < 0) { lane = ends.length; ends.push(0); }
      ends[lane] = it.left + it.width;
      return lane;
    });
  }
  function layoutTimeline(rows) {
    const LANE = 24, GAP = 8, PAD = 12;
    for (const track of rows.querySelectorAll(".row-track")) {
      const blocks = track.querySelector(".blocks"), spill = track.querySelector(".spill");
      const marks = track.querySelector(".marks"), W = blocks.clientWidth;
      if (!W) continue;
      spill.replaceChildren();
      const out = [];
      for (const node of blocks.querySelectorAll(".chord")) {
        const text = node.dataset.label, held = node.dataset.held === "1";
        const left = node.offsetLeft, width = node.offsetWidth;
        node.replaceChildren(held ? el("span", { class: "held" }, text) : text);
        node.removeAttribute("aria-hidden");
        if (measure(text, node) + PAD <= width) continue;
        // too long for the block: keep the text for screen readers, draw it below
        node.replaceChildren(el("span", { class: "visually-hidden" }, text));
        const probe = el("span", { class: "spill-label" + (held ? " held" : "") }, text);
        spill.append(probe);
        const w = measure(text, probe);
        const x = Math.min(Math.max(left + width / 2 - w / 2, 0), Math.max(W - w, 0));
        out.push({ probe, centre: left + width / 2, left: x, width: w });
      }
      const lanes = placeInLanes(out, GAP);
      out.forEach((o, i) => {
        const top = 8 + lanes[i] * LANE;
        Object.assign(o.probe.style, { left: `${o.left}px`, top: `${top}px` });
        o.probe.setAttribute("aria-hidden", "true");
        spill.append(el("div", { class: "leader", "aria-hidden": "true",
          style: { left: `${o.centre}px`, top: "0px", height: `${top + 2}px` } }));
      });
      spill.style.height = out.length ? `${8 + (Math.max(...lanes) + 1) * LANE}px` : "0px";
      // run markers: their own lanes above the blocks, flipped to the left near the right edge
      const mk = [...marks.querySelectorAll(".loop-mark")].map(m => {
        const x = Number(m.dataset.at) * W, w = measure(m.textContent, m) + 10;
        const flip = x + w > W;
        m.classList.toggle("flip", flip);
        return { m, x, flip, left: flip ? x - w : x, width: w };
      });
      const mlanes = placeInLanes(mk, GAP);
      const mh = mk.length ? (Math.max(...mlanes) + 1) * 20 : 0;
      marks.style.height = `${Math.max(mh, 6) + 6}px`;
      mk.forEach((o, i) => Object.assign(o.m.style, {
        left: `${o.flip ? o.x - o.width : o.x}px`, bottom: `${2 + mlanes[i] * 20}px` }));
    }
  }

  function unavailableBlock(title, reason) {
    return el("section", { class: "block" }, el("h2", {}, title), el("p", { class: "unavailable" }, reason));
  }

  // ---- header -------------------------------------------------------------------------
  const head = el("header", {},
    el("h1", {}, IDENTITY ? IDENTITY.title : `Track ${DATA.track.code}`),
    IDENTITY && IDENTITY.artist ? el("p", { class: "by" }, `by ${IDENTITY.artist}`) : null,
    el("p", { class: "meta" }, `${clock(DATA.track.duration_seconds)} long · analysed ${DATA.track.analysed_on}`),
    el("p", { class: "intro" }, "This is a reading of your song's chords and shape, made by software. Each finding " +
      "says where in the song it happens. Where the software couldn't work something out, this page says so."));
  page.append(head);
  document.title = IDENTITY ? `${IDENTITY.title}: uMuse reading` : `Track ${DATA.track.code}: uMuse reading`;

  // ---- harmony ----------------------------------------------------------------------------
  function harmonyBlock() {
    if (!harmony.available) return unavailableBlock("The chords", harmony.reason_if_unavailable);
    const src = harmony.chord_source, [from, to] = src.covers_seconds;
    // chords for the whole track (local Essentia) or only a stretch of it (Moises free plan)
    const whole = from <= 0 && to >= DATA.track.duration_seconds - 1;
    const local = src.tool !== "Moises";  // Essentia or Chordino, run by uMuse
    const kr = harmony.key_reading, keyName = `${harmony.key} ${harmony.mode}`;
    const b = el("section", { class: "block" }, el("h2", {}, "The chords that keep coming back"));

    if (harmony.loop) {
      const starts = harmony.loop.occurs_at_seconds;
      b.append(el("p", { class: "lead" }, "Your song keeps coming back to this run of chords: ",
        el("span", { class: "degrees" }, harmony.loop.degrees.join(" → ")), "."));
      const shown = starts.length > 8 ? [...starts.slice(0, 8).map(around), `${starts.length - 8} more times after that`]
                                      : starts.map(around);
      b.append(el("p", {}, (whole ? "Across the song" : `In the stretch we could read (${clock(from)}–${clock(to)})`) +
        `, this run starts ${starts.length} times: ${list(shown)}.`));
    }

    b.append(el("h3", {}, `Key: ${keyName}`));
    b.append(el("p", {}, `The chord numbers count from ${harmony.key}: I is the chord built on ${harmony.key}, ` +
      "IV the one built four notes up, and so on. Capitals are major chords, small letters minor."));
    // what points to a reading, in plain words, from key_reading (supported_by, most_heard, section_endings)
    const reasons = r => {
      const by = r.supported_by, out = [];
      const tests = by.filter(x => x.endsWith("key profile")).length;
      if (tests) out.push(`${tests === 3 ? "all three" : tests} key test${tests === 1 ? "" : "s"} point there`);
      if (by.includes("key shown by Moises")) out.push("Moises shows it");
      if (by.includes("most-heard chord") && kr.most_heard)
        out.push(`the chord heard longest (${kr.most_heard.degree}) is its home chord`);
      if (by.includes("chord at most section endings") && kr.section_endings) {
        const home = r.relation === "primary" ? (harmony.mode === "major" ? "I" : "i")
                   : (harmony.mode === "major" ? "vi" : "III");
        const ends = kr.section_endings, n = ends.filter(e => e.degree === home).length;
        const last = ends[ends.length - 1];
        const atEnd = last && last.degree === home && last.at_seconds >= DATA.track.duration_seconds - 0.5;
        out.push(`${n} of the ${ends.length} parts end on its home chord (${home})` + (atEnd ? ", including the end of the song" : ""));
      }
      return list(out);
    };
    if (kr.ambiguous) {
      const primary = kr.readings.find(r => r.relation === "primary");
      for (const r of kr.readings.filter(x => x.relation !== "primary")) {
        b.append(el("p", {}, r.relation === "relative"
          ? `This reads as ${keyName}: ${reasons(primary)}. But ${r.key} ${r.mode} uses the same notes, and ` +
            `${reasons(r)}. The analysis can't separate the two.`
          : `This reads as ${keyName} (${reasons(primary)}), but part of the analysis points to ${r.key} ${r.mode} ` +
            `instead (${reasons(r)}); it disagrees with itself here.`));
      }
    } else {
      const by = kr.readings[0].supported_by;
      const tests = by.filter(s => s.endsWith("key profile")).length;
      const moises = by.includes("key shown by Moises");
      b.append(el("p", {}, `${tests === 3 ? "Three" : tests} separate key tests` +
        (moises ? " and the key Moises shows all" : " all") + ` read ${keyName}.`));
    }
    const fit = KEY_FIT.find(([t]) => harmony.key_confidence >= t)[1];
    b.append(el("p", {}, `How clearly the notes point to ${keyName}: `,
      el("span", { class: "figure" }, fixed(harmony.key_confidence, 2)),
      ` on a 0–1 scale. ${fit} This is a fit score, not a percentage chance.`));
    if (kr.most_heard) {
      b.append(el("p", {}, `The chord heard longest ${whole ? "in the song" : `in the first ${to >= 60 && to < 61 ? "minute" : clock(to)}`} is `,
        el("span", { class: "degrees" }, kr.most_heard.degree),
        `, about ${Math.round(kr.most_heard.seconds)} seconds in all.`));
    }

    // timeline: blocks are placed exactly by time; labels too long for their block are laid out after render
    b.append(el("h3", {}, `Every chord change, ${clock(from)}–${clock(to)}`));
    b.append(el("p", { class: "note" }, "Each block is one chord, as long as it lasts. Solid blocks are major chords " +
      "and dashed blocks minor, as the numerals say: capitals major, small letters minor. A label too long for its " +
      "block sits just below it, joined by a short line. Marks above a row show where the repeating run starts."));
    const changes = harmony.chord_changes, rows = el("div", { class: "chord-rows" });
    for (let r0 = from; r0 < to; r0 += ROW_SECONDS) {
      const r1 = Math.min(r0 + ROW_SECONDS, to);
      const marks = el("div", { class: "marks" }), blocks = el("div", { class: "blocks" }), spill = el("div", { class: "spill" });
      changes.forEach((c, i) => {
        const end = i + 1 < changes.length ? changes[i + 1].at_seconds : to;
        const a = Math.max(c.at_seconds, r0), z = Math.min(end, r1);
        if (z <= a) return;
        const held = c.at_seconds < r0;   // carried over from the row before
        const text = held ? `(${chordLabel(c)})` : chordLabel(c);
        const kind = c.degree === "N" ? " none" : isMinor(c.degree) ? " minor" : "";
        blocks.append(el("div", { class: "chord" + kind, "data-label": text, "data-held": held ? "1" : "",
          style: { left: `${(a - r0) / ROW_SECONDS * 100}%`, width: `${(z - a) / ROW_SECONDS * 100}%` } },
          held ? el("span", { class: "held" }, text) : text));
      });
      for (const t of (harmony.loop ? harmony.loop.occurs_at_seconds : []))
        if (t >= r0 && t < r1) marks.append(el("div", { class: "loop-mark", "data-at": String((t - r0) / ROW_SECONDS) },
          `run starts around ${clock(t)}`));
      rows.append(el("div", { class: "chord-row" }, el("div", { class: "row-label" }, `${clock(r0)}–${clock(r1)}`),
        el("div", { class: "row-track" }, marks, blocks, spill)));
    }
    b.append(rows);
    layouts.push(() => layoutTimeline(rows));
    const kinds = [];
    const bass = changes.find(c => c.bass_degree);
    if (bass) kinds.push(`${bass.degree}/${bass.bass_degree} means the ${bass.degree} chord with ` +
      (bass.bass_degree === "I" ? "the key note (I)" : `the ${bass.bass_degree} note`) + " in the bass.");
    // one plain-language line for each kind of added note that actually appears
    const ADDED = { "7": "a seventh added", "maj7": "a major seventh added", "6": "a sixth added",
                    "dim": "a flattened fifth (diminished)", "aug": "a raised fifth (augmented)",
                    "7b5": "a seventh and a flattened fifth" };
    for (const [detail, words] of Object.entries(ADDED)) {
      const c = changes.find(x => x.detail === detail);
      if (c) kinds.push(`${c.degree}${detail} is the ${c.degree} chord with ${words}.`);
    }
    if (changes.some(c => c.degree === "N")) kinds.push("N marks a stretch where the software heard no clear chord.");
    if (kinds.length) b.append(el("p", { class: "note" }, kinds.join(" ")));
    if (src.beyond_coverage) b.append(el("p", {}, src.beyond_coverage));
    b.append(el("p", { class: "hedge" }, local
      ? `Chord estimates made by ${src.tool === "Chordino" ? "Chordino" : "the uMuse analysis"}; ` +
        "not checked by ear. A chord change can show up about a second after it happens."
      : `Chord estimates from ${src.tool}; not independently verified. Times are approximate.`));
    return b;
  }
  page.append(harmonyBlock());
  layouts.forEach(f => f());
  if (page._umuseResize) page._umuseResize.disconnect();   // a new reading replaces the last one's watcher
  if (window.ResizeObserver) {
    let lastWidth = 0;
    const ro = page._umuseResize = new ResizeObserver(entries => {
      const w = Math.round(entries[0].contentRect.width);
      if (w !== lastWidth) { lastWidth = w; layouts.forEach(f => f()); }
    });
    ro.observe(page);
  }

  // ---- structure --------------------------------------------------------------------------
  function structureBlock() {
    if (!structure.available) return unavailableBlock("The shape of the song", structure.reason_if_unavailable);
    const secs = structure.sections, dur = DATA.track.duration_seconds;
    const b = el("section", { class: "block" }, el("h2", {}, "The shape of the song"));
    b.append(el("p", { class: "lead" }, "The software split your song into ",
      el("span", { class: "figure" }, `${secs.length} parts`),
      " by listening for where the sound repeats and where it changes. It doesn't name them."));

    const map = el("div", { class: "map" });
    secs.forEach((s, i) => map.append(el("div", { class: "part" + (i === secs.length - 1 ? " last" : ""),
      style: { left: `${s.start_seconds / dur * 100}%`, width: `${(s.end_seconds - s.start_seconds) / dur * 100}%` } },
      String(i + 1))));
    if (harmony.available) {
      const [f, t] = harmony.chord_source.covers_seconds;
      map.append(el("div", { class: "read", style: { left: `${f / dur * 100}%`, width: `${(t - f) / dur * 100}%` } },
        "chords read"));
    }
    for (const s of secs) for (const t of s.repeats)
      map.append(el("div", { class: "return", style: { left: `${t / dur * 100}%` } }));
    b.append(map);
    b.append(el("ul", { class: "parts" }, secs.map((s, i) =>
      el("li", {}, el("b", {}, String(i + 1)), ` ${clock(s.start_seconds)}–${clock(s.end_seconds)}`))));
    b.append(el("p", { class: "note" }, "Numbered blocks are the parts in order, with their times listed above. " +
      "Dashed marks with a diamond, under the map, show where earlier material comes back. The line above the map marks the stretch whose chords were read."));

    const returns = secs.filter(s => s.repeats.length);
    if (returns.length) {
      b.append(el("ul", { class: "plain" }, returns.map(s => el("li", {},
        `The opening of the part starting ${around(s.start_seconds)} comes back ${list(s.repeats.map(around))}.`))));
    } else {
      b.append(el("p", {}, "The software found no part that comes back later in the song."));
    }

    const paced = secs.filter(s => s.chord_changes_per_beat);
    if (paced.length) {
      const pace = s => `once every ${fixed(1 / s.chord_changes_per_beat, 1)} beats in the part from ` +
        `${clock(s.start_seconds)} to ${clock(s.end_seconds)}`;
      const lead = paced.length === secs.length ? "How often the chords change" : "In the stretch with chords, how often the chords change";
      if (paced.length <= 2) b.append(el("p", {}, `${lead}: about ${list(paced.map(pace))}.`));
      else b.append(el("p", {}, `${lead}:`), el("ul", { class: "plain" }, paced.map(s => el("li", {}, `about ${pace(s)}`))));
    }
    const short = secs.filter(s => s.end_seconds - s.start_seconds < 10).length;
    b.append(el("p", { class: "hedge" }, "Where one part ends and the next begins is the software's estimate." +
      (short ? ` ${short} of the ${secs.length} parts are shorter than 10 seconds, and some of them may belong together.` : "")));
    return b;
  }
  page.append(structureBlock());

  // ---- tempo ------------------------------------------------------------------------------
  function tempoBlock() {
    if (!groove.available) return unavailableBlock("Tempo", groove.reason_if_unavailable);
    const bc = groove.beat_confidence, band = BEAT_BANDS.find(([edge]) => bc.value < edge)[1];
    return el("section", { class: "block" }, el("h2", {}, "Tempo"),
      el("p", { class: "lead" }, el("span", { class: "figure" }, `About ${Math.round(groove.bpm)} beats per minute.`)),
      el("p", {}, `How easy the beat was for the software to follow: ${fixed(bc.value, 1)} on its ` +
        `0–${fixed(bc.scale_max, 1)} scale. That is in the "${band}" band; ` +
        "above 3.5 counts as excellent, below 1 as very low."));
  }
  page.append(tempoBlock());

  // ---- melody -----------------------------------------------------------------------------
  page.append(music.melody.available ? null : el("section", { class: "block" },
    el("h2", {}, "Melody: not analysed yet"), el("p", { class: "unavailable" }, music.melody.reason_if_unavailable)));

  // ---- comparisons ------------------------------------------------------------------------
  function dimensionLine(name, d) {
    return d.available
      ? el("p", { class: "dim" }, el("span", { class: "label" }, `${name} ${fixed(d.score, 2)}: `), d.evidence)
      : el("p", { class: "dim off" }, el("span", { class: "label" }, `${name}: not available. `), d.reason_if_unavailable);
  }

  function comparisonsBlock() {
    const comp = DATA.comparisons, pc = DATA.population_context;
    const b = el("section", { class: "block" }, el("h2", {}, "Songs that line up with yours"));
    if (!comp.available) { b.append(el("p", { class: "unavailable" }, comp.reason_if_unavailable)); return b; }
    b.append(el("p", {}, "We compared your song with two collections of songs that people annotated by hand. " +
      "These are likenesses in how the chords move and how long the parts are. They are not about sound, lyrics or quality."));
    b.append(el("p", {}, "The chord comparison follows how far each chord moves to the next, so it holds " +
      "whichever key your song is heard in."));

    const groups = [
      { source: "McGill Billboard", prefix: "McGill Billboard", heading: basis => {
          const yrs = (basis || "").match(/(\d{4})–(\d{4})/);
          return `US chart songs${yrs ? `, ${yrs[1]}–${yrs[2]}` : ""} (McGill Billboard)`; } },
      { source: "Harmonix", prefix: "Harmonix Set", heading: () => "Western pop songs (Harmonix Set)" },
    ];
    for (const g of groups) {
      const matches = comp.matches.filter(m => m.source === g.source);
      if (!matches.length) continue;
      const stmts = pc.available ? pc.statements.filter(s => s.basis.startsWith(g.prefix)) : [];
      const box = el("div", { class: "corpus" }, el("h3", {}, g.heading(stmts.length ? stmts[0].basis : "")));
      if (stmts.length) box.append(el("p", { class: "note" }, stmts[0].basis));
      for (const s of stmts) box.append(el("p", {}, s.statement));
      for (const m of matches) {
        const card = el("div", { class: "match" }, el("h4", {}, m.title),
          el("p", { class: "who" }, m.artist + (m.year ? `, charted ${m.year}` : "")));
        if (m.overall_similarity !== undefined)
          card.append(el("p", {}, el("span", { class: "figure" }, `Overall ${fixed(m.overall_similarity, 2)}`),
            " on a 0–1 scale: the average of chords and shape."));
        card.append(dimensionLine("Chords", m.dimensions.harmony), dimensionLine("Shape", m.dimensions.structure));
        box.append(card);
      }
      b.append(box);
    }
    return b;
  }
  page.append(comparisonsBlock());

  // ---- footer -----------------------------------------------------------------------------
  const src = harmony.available ? harmony.chord_source : null;
  page.append(el("footer", {}, src && src.tool !== "Essentia" && src.observed_on
    ? `Chords read from ${src.tool} on ${src.observed_on}. Key, tempo and parts from the uMuse analysis, run ${DATA.track.analysed_on}.`
    : src && src.tool === "Chordino"
      ? `Chords by Chordino; key, tempo and parts from the uMuse analysis, run ${DATA.track.analysed_on}.`
      : `Chords, key, tempo and parts from the uMuse analysis, run ${DATA.track.analysed_on}.`));
}
