// `arrow`: an arrow drawn over the slide, pointing at an element (spec 8.9).
// The only runtime geometry in Lattice: element boxes exist only in the browser. Everything is
// measured in slide units (the design size), so the drawing is independent of the window scale.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const GAP = 6; // space between the arrow and the boxes it touches
  const TWEEN_MS = 280;

  function find(section, ref, slideId, path) {
    if (!ref) return null;
    if (/^[A-Za-z][A-Za-z0-9_-]*$/.test(ref)) {
      const el = section.querySelector(`#${CSS.escape(ref)}`) ||
        section.querySelector(`[data-instance="${CSS.escape(`${slideId}/${ref}`)}"]`);
      return path ? item(el, path) : el;
    }
    try { return section.querySelector(ref); } catch (e) { return null; }
  }
  const isList = (e) => !!e && (e.tagName === "UL" || e.tagName === "OL");
  // An item of a list (spec 8.9): `[2]` is the second `li`, `[-1]` the last; a further index descends into
  // the first list nested in that item. The build has checked the path (LT063).
  function item(list, path) {
    let el = list;
    for (let k = 0; k < path.length; k++) {
      if (k > 0) el = Array.from(el.children).find(isList);
      if (!isList(el)) return null;
      const items = Array.from(el.children).filter((c) => c.tagName === "LI");
      el = items[path[k] > 0 ? path[k] - 1 : items.length + path[k]];
      if (!el) return null;
    }
    return el;
  }

  // Box of an element in slide units, relative to the slide section: the extent of its contents when it
  // has some (a heading or a code line fills its whole row, but the arrow should point at the text).
  // A code segment (spec 8.10) is the union of its pieces, one per line it spans.
  function box(el, section) {
    const s = section.getBoundingClientRect();
    const scale = s.width / section.offsetWidth || 1;
    const rect = (e) => {
      let r = e.getBoundingClientRect();
      if (e.childNodes.length) {
        const range = document.createRange();
        range.selectNodeContents(e);
        if (e.tagName === "LI") { // a list item without the lists nested in it: its own lines
          const sub = Array.from(e.childNodes).findIndex(isList);
          if (sub >= 0) range.setEnd(e, sub);
        }
        const c = range.getBoundingClientRect();
        if (c.width > 0 && c.height > 0) r = c;
      }
      return r;
    };
    let parts = [el];
    if (el.dataset && el.dataset.ltSeg) {
      const code = el.closest(".lt-code") || section;
      parts = Array.from(code.querySelectorAll(`[data-lt-seg="${CSS.escape(el.dataset.ltSeg)}"]`));
    }
    let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
    for (const p of parts) {
      const q = rect(p);
      l = Math.min(l, q.left); t = Math.min(t, q.top); r = Math.max(r, q.right); b = Math.max(b, q.bottom);
    }
    return { x: (l - s.left) / scale, y: (t - s.top) / scale, w: (r - l) / scale, h: (b - t) / scale };
  }
  // Box of the marker of a list item, in slide units (spec 8.9). A marker has no box in the page: with the
  // item's marker set inside for the time of one measurement, its first character moves right by the width
  // of the marker, which outside ends where the item's content starts. Exact for text markers (the built-in
  // stylesheet's bullets, and numbers); vertically, the marker is centered on the first character.
  function markerBox(li, section) {
    const s = section.getBoundingClientRect();
    const scale = s.width / section.offsetWidth || 1;
    const walker = document.createTreeWalker(li, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (!n.data.trim() ? NodeFilter.FILTER_SKIP
        : n.parentElement.closest("ul, ol") !== li.parentElement ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    });
    const text = walker.nextNode();
    const lr = li.getBoundingClientRect();
    const cs = getComputedStyle(li);
    const start = lr.left + li.clientLeft + parseFloat(cs.paddingLeft); // where the item's content starts
    let top = lr.top, height = parseFloat(cs.lineHeight) || lr.height, width = 0;
    if (text) {
      const i = text.data.search(/\S/);
      const range = document.createRange();
      range.setStart(text, i);
      range.setEnd(text, i + 1);
      const before = range.getBoundingClientRect();
      const saved = li.style.listStylePosition;
      li.style.listStylePosition = "inside";
      const after = range.getBoundingClientRect();
      li.style.listStylePosition = saved;
      width = Math.max(0, after.left - before.left);
      top = before.top;
      height = before.height;
    }
    const left = start - width;
    return { x: (left - s.left) / scale, y: (top - s.top) / scale, w: width / scale, h: height / scale };
  }
  // The largest length along `u` from `p` that stays inside the slide, with a margin.
  function room(p, u, section, margin) {
    const W = section.offsetWidth, H = section.offsetHeight;
    const lim = (pos, dir, max) => (dir > 0 ? (max - margin - pos) / dir : dir < 0 ? (margin - pos) / dir : Infinity);
    return Math.max(0, Math.min(lim(p.x, u.x, W), lim(p.y, u.y, H)));
  }
  const center = (b) => ({ x: b.x + b.w / 2, y: b.y + b.h / 2 });
  // Where a ray from the center of `b` along the unit vector `u` leaves the box.
  function exit(b, u) {
    const c = center(b);
    const t = Math.min(u.x ? Math.abs(b.w / 2 / u.x) : Infinity, u.y ? Math.abs(b.h / 2 / u.y) : Infinity);
    return { x: c.x + u.x * t, y: c.y + u.y * t };
  }
  const norm = (v) => { const l = Math.hypot(v.x, v.y) || 1; return { x: v.x / l, y: v.y / l }; };
  const lerp = (a, b, t) => a + (b - a) * t;
  // Unit vector of an angle in degrees, counterclockwise on screen (y goes down), 0 pointing right.
  const dir = (deg) => { const a = (deg * Math.PI) / 180; return { x: Math.cos(a), y: -Math.sin(a) }; };
  const anchored = (a) => typeof a === "number";

  // One end of an arrow between two boxes: its point on the box `b` and the direction it leaves the box
  // in (away from the box). An angle anchor (sides are angles, spec 8.9) fixes both; `center` is the
  // center itself; otherwise the end aims at `toward`, the other end's reference point.
  function end(b, anchor, toward) {
    if (anchored(anchor)) {
      const d = dir(anchor);
      const p = exit(b, d);
      return { p: { x: p.x + d.x * GAP, y: p.y + d.y * GAP }, d, fixed: true };
    }
    const c = center(b);
    const d = norm({ x: toward.x - c.x, y: toward.y - c.y });
    if (anchor === "center") return { p: c, d, fixed: false };
    const p = exit(b, d);
    return { p: { x: p.x + d.x * GAP, y: p.y + d.y * GAP }, d, fixed: false };
  }
  // The point another end aims at: an anchored end's point on its box, else the box center.
  const ref = (b, anchor) => (anchored(anchor) ? exit(b, dir(anchor)) : center(b));

  // A cubic curve from `tail` to `head`. An end with a fixed direction leaves (or enters) along it; a free
  // end follows the chord, so with two free ends the curve is the quadratic of the earlier versions,
  // bent sideways by `curve` times its length.
  function curveOf(tail, head, dTail, dHead, curve) {
    const len = Math.hypot(tail.x - head.x, tail.y - head.y);
    const u = norm({ x: tail.x - head.x, y: tail.y - head.y }); // from the head toward the tail
    const perp = { x: -u.y, y: u.x };
    const bend = (curve * len * 2) / 3;
    const reach = Math.min(Math.max(len * 0.45, 40), 260); // handle of an end with a fixed direction
    const h1 = dTail ? { x: dTail.x * reach, y: dTail.y * reach } : { x: -u.x * len / 3, y: -u.y * len / 3 };
    const h2 = dHead ? { x: dHead.x * reach, y: dHead.y * reach } : { x: u.x * len / 3, y: u.y * len / 3 };
    return {
      tail, head, perp,
      c1: { x: tail.x + h1.x + perp.x * bend, y: tail.y + h1.y + perp.y * bend },
      c2: { x: head.x + h2.x + perp.x * bend, y: head.y + h2.y + perp.y * bend },
    };
  }

  // Geometry of one step: tail, head, control points of the curve and where the label goes.
  const written = (ref, path) => ref + (path ? path.map((n) => `[${n}]`).join("") : "");
  // The box an end is measured on, and its anchor: a `bullet` end is the left side of the item's marker.
  function endBox(el, anchor, section) {
    if (anchor === "bullet") return el.tagName === "LI" ? [markerBox(el, section), 180] : [box(el, section), 180];
    return [box(el, section), anchor];
  }

  function geometry(inst, step) {
    const target = find(inst.section, step.to, inst.slideId, step.to_item);
    if (!target) {
      console.warn(`lattice: arrow target ${written(step.to, step.to_item)} not found on slide ${inst.slideId}`);
      return null;
    }
    const [tb, toAnchor] = endBox(target, step.to_anchor, inst.section);
    step = Object.assign({}, step, { to_anchor: toAnchor });
    const from = step.from ? find(inst.section, step.from, inst.slideId, step.from_item) : null;
    let g, label;
    if (from) {
      const [fb, fromAnchor] = endBox(from, step.from_anchor, inst.section);
      step.from_anchor = fromAnchor;
      const t = end(fb, step.from_anchor, ref(tb, step.to_anchor));
      const h = end(tb, step.to_anchor, ref(fb, step.from_anchor));
      g = curveOf(t.p, h.p, t.fixed ? t.d : null, h.fixed ? h.d : null, inst.curve);
      const mid = { x: (g.tail.x + 3 * g.c1.x + 3 * g.c2.x + g.head.x) / 8, y: (g.tail.y + 3 * g.c1.y + 3 * g.c2.y + g.head.y) / 8 };
      const off = 14 * Math.sign(inst.curve || 1);
      label = { x: mid.x + g.perp.x * off, y: mid.y + g.perp.y * off, anchor: "middle", base: g.perp.y > 0 ? "hanging" : "auto" };
    } else {
      const u = dir(step.angle); // from the target toward the tail
      let head0, dHead = null;
      if (anchored(step.to_anchor)) {
        dHead = dir(step.to_anchor);
        head0 = exit(tb, dHead);
      } else if (step.to_anchor === "center") {
        head0 = center(tb);
      } else {
        head0 = exit(tb, u);
      }
      const length = Math.min(step.length, room(head0, u, inst.section, 24) - GAP);
      const tail = { x: head0.x + u.x * (GAP + length), y: head0.y + u.y * (GAP + length) };
      const push = step.to_anchor === "center" ? 0 : GAP;
      const hd = dHead || u;
      const head = { x: head0.x + hd.x * push, y: head0.y + hd.y * push };
      g = curveOf(tail, head, null, dHead, inst.curve);
      label = { x: tail.x + u.x * 10, y: tail.y + u.y * 10,
        anchor: u.x > 0.3 ? "start" : u.x < -0.3 ? "end" : "middle", base: u.y > 0.3 ? "hanging" : u.y < -0.3 ? "auto" : "middle" };
    }
    return { tail: g.tail, head: g.head, c1: g.c1, c2: g.c2, label, text: step.label || "" };
  }

  function draw(inst, g) {
    inst.drawn = g;
    const { tail, head, c1, c2 } = g;
    const f = (p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    inst.path.setAttribute("d", `M${f(tail)} C${f(c1)} ${f(c2)} ${f(head)}`);
    inst.text.textContent = g.text;
    inst.text.setAttribute("x", g.label.x.toFixed(1));
    inst.text.setAttribute("y", g.label.y.toFixed(1));
    inst.text.setAttribute("text-anchor", g.label.anchor);
    inst.text.setAttribute("dominant-baseline", g.label.base);
    inst.text.style.display = g.text ? "" : "none";
    if (g.text) { // keep the label inside the slide
      const W = inst.section.offsetWidth;
      const bb = inst.text.getBBox();
      const dx = bb.x + bb.width > W - 12 ? W - 12 - (bb.x + bb.width) : bb.x < 12 ? 12 - bb.x : 0;
      if (dx) inst.text.setAttribute("x", (g.label.x + dx).toFixed(1));
    }
  }

  function mix(a, b, t) {
    const pt = (p, q) => ({ x: lerp(p.x, q.x, t), y: lerp(p.y, q.y, t) });
    return { tail: pt(a.tail, b.tail), head: pt(a.head, b.head), c1: pt(a.c1, b.c1), c2: pt(a.c2, b.c2),
      label: Object.assign({}, b.label, pt(a.label, b.label)), text: b.text };
  }

  // `timing` ({delay, duration} in ms, from an `lt-relayout` event) makes the glide follow the content.
  function update(inst, animate, timing) {
    const step = inst.steps[Math.max(0, Math.min(inst.position, inst.steps.length - 1))];
    const svg = inst.svg;
    svg.setAttribute("viewBox", `0 0 ${inst.section.offsetWidth} ${inst.section.offsetHeight}`);
    const g = step ? geometry(inst, step) : null; // a null step: no arrow at this position (spec 8.9)
    cancelAnimationFrame(inst.raf);
    svg.style.visibility = g ? "" : "hidden";
    if (!g) {
      inst.drawn = inst.last = null; // the next arrow appears in place, it does not glide from here
      return;
    }
    if (animate && (inst.drawn || inst.last)) {
      const from = inst.drawn || inst.last; // from what is on screen, even halfway through a glide
      const t0 = performance.now() + ((timing && timing.delay) || 0);
      const ms = (timing && timing.duration) || TWEEN_MS;
      const frame = (now) => {
        const t = Math.max(0, Math.min(1, (now - t0) / ms));
        const e = timing ? (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2) : 1 - (1 - t) * (1 - t);
        draw(inst, mix(from, g, e));
        if (t < 1) inst.raf = requestAnimationFrame(frame);
      };
      inst.raf = requestAnimationFrame(frame);
    } else {
      draw(inst, g);
    }
    inst.last = g;
  }

  Lattice.component("arrow", {
    mount(el, data, api) {
      const section = el.closest(".lt-slide");
      const slideId = section.dataset.slide;
      section.appendChild(el); // an overlay over the whole slide, above the content
      el.classList.add("lt-arrow-overlay");
      const markerId = `lt-arrow-head-${api.instanceId.replace(/[^A-Za-z0-9_-]/g, "_")}`;
      const color = data.color || "var(--lt-accent)";
      const svg = document.createElementNS(NS, "svg");
      svg.innerHTML = `<defs><marker id="${markerId}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${color}"/></marker></defs>` +
        `<path class="lt-arrow-line" stroke="${color}" stroke-width="${data.width}" marker-end="url(#${markerId})"/>` +
        `<text class="lt-arrow-text" fill="${color}"></text>`;
      el.querySelector(".lt-arrow-box").appendChild(svg);
      const inst = { el, svg, section, slideId, steps: data.steps, curve: data.curve || 0, position: 0, last: null,
        raf: 0, path: svg.querySelector("path.lt-arrow-line"), text: svg.querySelector("text") };
      const relayout = () => { if (!section.hidden) update(inst, false); };
      api.onResize(relayout);
      if (window.ResizeObserver) {
        inst.observer = new ResizeObserver(relayout);
        const body = section.querySelector(".lt-body");
        if (body) inst.observer.observe(body);
      }
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(relayout);
      // a component moved content of the slide (a code-morph changing its text, spec 10.4)
      // (after every show of this step, so that the arrow's own step, if any, is the one measured)
      section.addEventListener("lt-relayout", (e) => {
        const d = e.detail || {};
        queueMicrotask(() => { if (!section.hidden) update(inst, !!d.animate, d.timing); });
      });
      return inst;
    },
    show(inst, position, info) {
      inst.position = position;
      update(inst, !!(info && info.animate));
    },
    enter(inst) {
      requestAnimationFrame(() => { if (!inst.section.hidden) update(inst, false); }); // once the slide has its layout
    },
    leave(inst) {
      cancelAnimationFrame(inst.raf);
    },
    destroy(inst) {
      if (inst.observer) inst.observer.disconnect();
    },
  });
})();
