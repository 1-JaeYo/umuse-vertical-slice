// Background wallpaper of hand-drawn music symbols, after the researcher's sketch: notes, beamed
// notes, clefs, accidentals and rests, scattered at slight angles in muted dark greens in the margins either side of the main column.
// Placement is seeded, so the layout is the same on every load. Decoration only: aria-hidden,
// ignores the pointer, and sits behind the panels (the glass blurs it further).
(function () {
  const NS = "http://www.w3.org/2000/svg";

  // Each symbol is drawn in a 100x100 box. Strokes are the pen line; `head`/`dot` are filled.
  const head = (x, y, open) =>
    `<ellipse class="${open ? "" : "fill"}" cx="${x}" cy="${y}" rx="12" ry="8.5" transform="rotate(-28 ${x} ${y})"/>`;
  const dot = (x, y, r = 4) => `<circle class="fill" cx="${x}" cy="${y}" r="${r}"/>`;
  const flag = y => `<path d="M51 ${y}C55 ${y + 6} 66 ${y + 9} 69 ${y + 16}C71 ${y + 20} 71 ${y + 24} 70 ${y + 28}"/>`;
  const restHook = (x, y) => `${dot(x, y, 5)}<path d="M${x} ${y + 5}C${x + 10} ${y + 8} ${x + 20} ${y + 2} ${x + 26} ${y - 6}"/>`;
  const flat = x => `<path d="M${x} 10L${x} 86C${x + 18} 78 ${x + 26} 68 ${x + 22} 60C${x + 18} 52 ${x + 8} 56 ${x} 64"/>`;

  const SYMBOLS = [
    `<ellipse cx="50" cy="52" rx="17" ry="11.5" transform="rotate(-12 50 52)"/>`,                     // whole
    `${head(40, 80, true)}<path d="M51 75C51 55 52 30 53 10"/>`,                                      // half
    `${head(40, 80)}<path d="M51 76L51 10"/>`,                                                        // quarter
    `${head(40, 82)}<path d="M51 78L52 8"/>${flag(8)}`,                                               // eighth
    `${head(40, 84)}<path d="M51 80L52 8"/>${flag(8)}${flag(20)}`,                                    // sixteenth
    `${head(40, 88)}<path d="M51 84L52 4"/>${flag(4)}${flag(15)}${flag(26)}`,                         // thirty-second
    `${head(22, 82)}${head(72, 80)}<path d="M33 78L33 22M83 76L84 20"/><path class="beam" d="M33 22L84 20"/>`,  // beamed eighths
    `${head(22, 82)}${head(72, 80)}<path d="M33 78L33 22M83 76L84 20"/><path class="beam" d="M33 22L84 20M33 34L84 32"/>`,
    `${head(22, 88)}${head(70, 70)}<path d="M33 84L34 26M81 66L80 8"/><path class="beam" d="M34 26L80 8"/>`,
    `${head(22, 90)}${head(70, 72)}<path d="M33 86L34 26M81 68L80 8"/><path class="beam" d="M34 26L80 8M34 38L80 20"/>`,
    `<path d="M46 92C38 98 28 90 34 84C40 79 48 84 45 90L56 10C58 2 68 6 64 16C60 28 30 40 30 62C30 80 56 82 63 70C69 59 58 48 48 52C40 56 42 66 50 66"/>`,  // treble clef
    `<path d="M28 42C28 22 60 18 66 36C72 58 52 76 26 88"/>${dot(80, 32)}${dot(80, 50)}${dot(31, 42, 6)}`,  // bass clef
    `<path d="M40 14L40 90M60 10L60 86"/><path class="beam" d="M26 44L74 33M26 66L74 55"/>`,         // sharp
    flat(38),                                                                                         // flat
    `<g transform="translate(50 0) scale(0.92 1) translate(-50 0)">${flat(18)}${flat(56)}</g>`,      // double flat
    `<path d="M36 10L36 72L64 64M36 40L64 32L64 92"/>`,                                               // natural
    `${restHook(34, 30)}<path d="M60 24L46 90"/>`,                                                    // eighth rest
    `${restHook(36, 24)}${restHook(30, 46)}<path d="M62 14L46 92"/>`,                                 // sixteenth rest
    `${restHook(40, 16)}${restHook(34, 38)}${restHook(28, 60)}<path d="M68 6L50 96"/>`,               // thirty-second rest
    `${head(46, 32)}<path d="M35 36L36 96"/>${dot(50, 12)}`,                                          // staccato
    `${head(46, 34)}<path d="M35 38L36 96M30 14L62 12"/>`,                                            // tenuto
  ];

  function random(seed) {  // the same seeded generator as sketch.js (mulberry32)
    return () => {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Symbols go only in the side margins, left and right of the main column, never behind it.
  const CELL = 190;     // one symbol per cell of a jittered grid in each margin, so they spread out evenly
  const CLEAR = 36;     // gap kept between the symbols and the column
  const MIN_GUTTER = 90;  // narrower margins (phone width) get no symbols
  const layer = document.createElement("div");
  layer.className = "music-bg";
  layer.setAttribute("aria-hidden", "true");
  document.body.prepend(layer);

  function draw() {
    const w = window.innerWidth, h = window.innerHeight;
    // the column is the form, widened to the results once a reading is on the page
    const parts = [document.getElementById("upload"), document.getElementById("page")]
      .filter(el => el && el.childElementCount !== 0 && el.offsetWidth);
    const boxes = parts.length ? parts.map(el => el.getBoundingClientRect()) : [document.querySelector("main").getBoundingClientRect()];
    const box = { left: Math.min(...boxes.map(b => b.left)), right: Math.max(...boxes.map(b => b.right)) };
    const gutters = [[0, box.left - CLEAR], [box.right + CLEAR, w]].filter(([a, b]) => b - a >= MIN_GUTTER);
    const rnd = random(1987);
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("width", w);
    svg.setAttribute("height", h);
    let order = [];
    let out = "";
    for (const [left, right] of gutters) {
      const cols = Math.max(1, Math.round((right - left) / CELL)), cellW = (right - left) / cols;
      const rows = Math.ceil(h / CELL), cellH = h / rows;
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if (!order.length) order = SYMBOLS.map((_, i) => i).sort(() => rnd() - 0.5);  // every symbol before any repeats
          if (rnd() < 0.2) continue;  // leave a few cells empty: sparse, not a pattern
          const i = order.pop();
          const size = Math.min(44 + rnd() * 26, cellW * 0.8);
          // jitter within the cell, keeping the whole symbol inside it (so inside the margin)
          const x = left + c * cellW + rnd() * (cellW - size);
          const y = r * cellH + rnd() * Math.max(0, cellH - size);
          const angle = (rnd() - 0.5) * 30;
          const tone = 1 + Math.floor(rnd() * 2);
          out += `<g class="tone${tone}" transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${angle.toFixed(1)} ${size / 2} ${size / 2}) scale(${(size / 100).toFixed(3)})">${SYMBOLS[i]}</g>`;
        }
      }
    }
    svg.innerHTML = out;
    layer.replaceChildren(svg);
  }

  draw();
  let pending = 0;
  const redraw = () => { cancelAnimationFrame(pending); pending = requestAnimationFrame(draw); };
  window.addEventListener("resize", redraw);
  const page = document.getElementById("page");  // a reading arriving (or clearing) changes the column
  if (page && window.MutationObserver) new MutationObserver(redraw).observe(page, { childList: true });
})();
