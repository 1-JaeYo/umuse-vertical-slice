// Hand-drawn outlines for the upload view, after the researcher's sketch: a wobbly solid edge for
// the form panel, a wobbly dashed edge for the file well, and a wobbly outline for Choose File.
// Each outline is an SVG drawn at the element's real size and redrawn when it resizes. A fixed
// seed per element keeps the wobble the same every time, so nothing jitters. Decoration only:
// every SVG is aria-hidden and ignores the pointer.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const PAD = 4;  // room outside the box for the wobble

  function random(seed) {  // small seeded generator (mulberry32)
    return () => {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Points around a rounded rectangle, each pushed in or out along its normal by a little noise.
  function wobblyPoints(w, h, r, amp, seed, step) {
    const rnd = random(seed), pts = [];
    const push = (x, y, nx, ny) => { const o = (rnd() * 2 - 1) * amp; pts.push([x + nx * o, y + ny * o]); };
    const edge = (x0, y0, x1, y1, nx, ny) => {
      const len = Math.hypot(x1 - x0, y1 - y0), n = Math.max(1, Math.round(len / step));
      for (let i = 0; i < n; i++) push(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, nx, ny);
    };
    const corner = (cx, cy, from) => {
      for (let a = from; a < from + 90; a += 30) {
        const t = a * Math.PI / 180, c = Math.cos(t), s = Math.sin(t);
        push(cx + r * c, cy + r * s, c, s);
      }
    };
    edge(r, 0, w - r, 0, 0, -1);          corner(w - r, r, -90);
    edge(w, r, w, h - r, 1, 0);           corner(w - r, h - r, 0);
    edge(w - r, h, r, h, 0, 1);           corner(r, h - r, 90);
    edge(0, h - r, 0, r, -1, 0);          corner(r, r, 180);
    return pts;
  }

  // A smooth closed curve through the points (Catmull-Rom as cubic Béziers).
  function curve(pts) {
    const n = pts.length, p = i => pts[(i + n) % n];
    let d = `M${p(0)[0].toFixed(1)} ${p(0)[1].toFixed(1)}`;
    for (let i = 0; i < n; i++) {
      const [a, b, c, e] = [p(i - 1), p(i), p(i + 1), p(i + 2)];
      d += `C${(b[0] + (c[0] - a[0]) / 6).toFixed(1)} ${(b[1] + (c[1] - a[1]) / 6).toFixed(1)} ` +
           `${(c[0] - (e[0] - b[0]) / 6).toFixed(1)} ${(c[1] - (e[1] - b[1]) / 6).toFixed(1)} ` +
           `${c[0].toFixed(1)} ${c[1].toFixed(1)}`;
    }
    return d + "Z";
  }

  // Attach an outline to `host`. `box` (optional) gives the outlined area inside host in px;
  // by default the whole host is outlined.
  function sketch(host, { cls, seed, radius = 14, amp = 1.6, step = 34, box }) {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", `sketch ${cls}`);
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const fill = document.createElementNS(NS, "path"), line = document.createElementNS(NS, "path");
    fill.setAttribute("class", "sketch-fill");
    line.setAttribute("class", "sketch-line");
    svg.append(fill, line);
    host.prepend(svg);
    const draw = () => {
      const r = box ? box() : { x: 0, y: 0, w: host.clientWidth, h: host.clientHeight };
      if (!r.w || !r.h) return;
      Object.assign(svg.style, { left: `${r.x - PAD}px`, top: `${r.y - PAD}px`,
                                 width: `${r.w + PAD * 2}px`, height: `${r.h + PAD * 2}px` });
      svg.setAttribute("viewBox", `${-PAD} ${-PAD} ${r.w + PAD * 2} ${r.h + PAD * 2}`);
      const d = curve(wobblyPoints(r.w, r.h, Math.min(radius, r.h / 2 - 1), amp, seed, step));
      fill.setAttribute("d", d);
      line.setAttribute("d", d);
    };
    draw();
    if (window.ResizeObserver) new ResizeObserver(draw).observe(host);
    return draw;
  }

  const form = document.getElementById("upload");
  const well = document.querySelector(".file-well");
  const input = document.getElementById("audio");
  if (!form || !well || !input) return;
  document.documentElement.classList.add("sketched");   // CSS drops the straight borders only when this ran
  sketch(form, { cls: "sketch-panel", seed: 11, radius: 26, amp: 2.2, step: 46 });
  sketch(well, { cls: "sketch-well", seed: 23, radius: 20, amp: 1.8, step: 36 });
  // Choose File is the input's built-in button, sized in CSS (--choose-w by --choose-h), so its box is known
  const chooseDraw = sketch(well, {
    cls: "sketch-choose", seed: 37, radius: 12, amp: 1.2, step: 22,
    box: () => {
      const cs = getComputedStyle(well);
      const w = parseFloat(cs.getPropertyValue("--choose-w")), h = parseFloat(cs.getPropertyValue("--choose-h"));
      return { x: input.offsetLeft, y: input.offsetTop + (input.offsetHeight - h) / 2, w, h };
    },
  });
  if (window.ResizeObserver) new ResizeObserver(chooseDraw).observe(input);
})();
