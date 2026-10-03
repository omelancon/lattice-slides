// Line and segment highlighting for `code` (as a follower) and `code-steps` (spec 8.8, 8.10).
(() => {
  const controller = {
    mount(el, data) {
      const box = el.querySelector(".lt-code");
      const lines = new Map(Array.from(el.querySelectorAll(".lt-line")).map((l) => [Number(l.dataset.line), l]));
      const segs = new Map(); // name -> its pieces (a segment spanning lines has one piece per line)
      for (const p of el.querySelectorAll(".lt-seg")) {
        if (!segs.has(p.dataset.ltSeg)) segs.set(p.dataset.ltSeg, []);
        segs.get(p.dataset.ltSeg).push(p);
      }
      return { box, lines, segs, steps: (data && data.steps) || [[]], segSteps: (data && data.segs) || null,
        pre: el.querySelector("pre") };
    },
    show(inst, position, info) {
      const hl = new Set(inst.steps[position] || []);
      const on = new Set(inst.segSteps ? inst.segSteps[position] || [] : []);
      const holders = new Set(); // lines holding a highlighted segment stay undimmed
      for (const [name, parts] of inst.segs) {
        const lit = on.has(name);
        for (const p of parts) {
          p.classList.toggle("lt-hl", lit);
          if (lit) holders.add(p.closest(".lt-line"));
        }
      }
      let first = null;
      for (const [n, line] of inst.lines) {
        const lit = hl.has(n);
        line.classList.toggle("lt-hl", lit);
        line.classList.toggle("lt-hl-in", holders.has(line));
        if ((lit || holders.has(line)) && !first) first = line;
      }
      inst.box.classList.toggle("lt-has-hl", hl.size > 0 || on.size > 0);
      if (first && inst.pre.scrollHeight > inst.pre.clientHeight) {
        // the line's offset inside the scrolled box (offsetTop counts from the slide, its offsetParent),
        // in the box's own pixels: the slide may be scaled to the window
        const pre = inst.pre;
        const box = pre.getBoundingClientRect();
        const scale = box.height / pre.offsetHeight || 1;
        const top = (first.getBoundingClientRect().top - box.top) / scale + pre.scrollTop;
        pre.scrollTo({ top: Math.max(0, top - pre.clientHeight / 3), behavior: info && info.animate ? "smooth" : "auto" });
      }
    },
  };
  Lattice.component("code", controller);
  Lattice.component("code-steps", controller);
})();
