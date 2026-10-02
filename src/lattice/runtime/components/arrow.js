// `arrow`: an arrow drawn over the slide, pointing at an element (spec 8.9).
// The only runtime geometry in Lattice: element boxes exist only in the browser. Everything is
// measured in slide units (the design size), so the drawing is independent of the window scale.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const GAP = 6; // space between the arrow and the boxes it touches
  const TWEEN_MS = 280;

  function find(section, ref, slideId) {
    if (!ref) return null;
    if (/^[A-Za-z][A-Za-z0-9_-]*$/.test(ref)) {
      return section.querySelector(`#${CSS.escape(ref)}`) ||
        section.querySelector(`[data-instance="${CSS.escape(`${slideId}/${ref}`)}"]`);
    }
    try { return section.querySelector(ref); } catch (e) { return null; }
  }

  // Box of an element in slide units, relative to the slide section: the extent of its contents when it
  // has some (a heading or a code line fills its whole row, but the arrow should point at the text).
  function box(el, section) {
    const s = section.getBoundingClientRect();
    const scale = s.width / section.offsetWidth || 1;
    let r = el.getBoundingClientRect();
    if (el.childNodes.length) {
      const range = document.createRange();
      range.selectNodeContents(el);
      const c = range.getBoundingClientRect();
      if (c.width > 0 && c.height > 0) r = c;
    }
    return { x: (r.left - s.left) / scale, y: (r.top - s.top) / scale, w: r.width / scale, h: r.height / scale };
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

  // Geometry of one step: tail, head, control point of the curve and where the label goes.
  function geometry(inst, step) {
    const target = find(inst.section, step.to, inst.slideId);
    if (!target) {
      console.warn(`lattice: arrow target ${step.to} not found on slide ${inst.slideId}`);
      return null;
    }
    const tb = box(target, inst.section);
    let u, tail, head; // u points from the head toward the tail
    const from = step.from ? find(inst.section, step.from, inst.slideId) : null;
    if (from) {
      const fb = box(from, inst.section);
      u = norm({ x: center(fb).x - center(tb).x, y: center(fb).y - center(tb).y });
      tail = exit(fb, { x: -u.x, y: -u.y });
      head = exit(tb, u);
      tail = { x: tail.x - u.x * GAP, y: tail.y - u.y * GAP };
    } else {
      const a = (step.angle * Math.PI) / 180;
      u = { x: Math.cos(a), y: -Math.sin(a) }; // counterclockwise on screen: y goes down
      head = exit(tb, u);
      const length = Math.min(step.length, room(head, u, inst.section, 24) - GAP);
      tail = { x: head.x + u.x * (GAP + length), y: head.y + u.y * (GAP + length) };
    }
    head = { x: head.x + u.x * GAP, y: head.y + u.y * GAP };
    const len = Math.hypot(tail.x - head.x, tail.y - head.y);
    const mid = { x: (tail.x + head.x) / 2, y: (tail.y + head.y) / 2 };
    const perp = { x: -u.y, y: u.x };
    const bend = inst.curve * len;
    const ctrl = { x: mid.x + perp.x * bend, y: mid.y + perp.y * bend };
    let label;
    if (from) {
      const off = bend / 2 + 14 * Math.sign(bend || 1);
      label = { x: mid.x + perp.x * off, y: mid.y + perp.y * off, anchor: "middle", base: perp.y > 0 ? "hanging" : "auto" };
    } else {
      label = { x: tail.x + u.x * 10, y: tail.y + u.y * 10,
        anchor: u.x > 0.3 ? "start" : u.x < -0.3 ? "end" : "middle", base: u.y > 0.3 ? "hanging" : u.y < -0.3 ? "auto" : "middle" };
    }
    return { tail, head, ctrl, label, text: step.label || "" };
  }

  function draw(inst, g) {
    const { tail, head, ctrl } = g;
    inst.path.setAttribute("d", `M${tail.x.toFixed(1)},${tail.y.toFixed(1)} Q${ctrl.x.toFixed(1)},${ctrl.y.toFixed(1)} ${head.x.toFixed(1)},${head.y.toFixed(1)}`);
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
    return { tail: pt(a.tail, b.tail), head: pt(a.head, b.head), ctrl: pt(a.ctrl, b.ctrl),
      label: Object.assign({}, b.label, pt(a.label, b.label)), text: b.text };
  }

  function update(inst, animate) {
    const step = inst.steps[Math.max(0, Math.min(inst.position, inst.steps.length - 1))];
    const svg = inst.svg;
    svg.setAttribute("viewBox", `0 0 ${inst.section.offsetWidth} ${inst.section.offsetHeight}`);
    const g = geometry(inst, step);
    cancelAnimationFrame(inst.raf);
    svg.style.visibility = g ? "" : "hidden";
    if (!g) return;
    if (animate && inst.last) {
      const from = inst.last;
      const t0 = performance.now();
      const frame = (now) => {
        const t = Math.min(1, (now - t0) / TWEEN_MS);
        const e = 1 - (1 - t) * (1 - t);
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
