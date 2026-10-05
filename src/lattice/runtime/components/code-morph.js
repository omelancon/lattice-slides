// `code-morph` (spec 8.11): code whose text changes between positions. The build aligned the versions;
// each unit is an element placed on a monospace grid (`--r` rows, `--c` columns), so showing a version is
// setting two numbers per unit. On a single step CSS transitions make the change visible: leaving units
// fade out, surviving ones glide, arriving ones fade in. Every other move places the units directly.
// A transparent copy of the current text lies on top, for selection and for arrows (its segments).
// Highlights (built per position) are painted under the units by two layer slots that cross-fade, and
// units outside the highlighted rows are dimmed.
(() => {
  const QUICK = 140; // ms of the unphased glide used when a step arrives during a change

  const reduced = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  // Tell measuring runtimes (arrows) that the text moved; `timing` is when the surviving units glide.
  function relayout(inst, animate, timing) {
    inst.el.dispatchEvent(new CustomEvent("lt-relayout", { bubbles: true, detail: { animate, timing } }));
  }

  // The class of a unit at version `v`: its Pygments class there (or the last one it had), then its role.
  function unitClass(inst, i, v, role) {
    const p = inst.d.pos[i][v];
    if (p) inst.cls[i] = inst.d.classes[p[2]];
    return `lt-mt${inst.cls[i] ? ` ${inst.cls[i]}` : ""}${role}`;
  }

  function place(inst, v, mode) {
    const { d, toks, lns, prev } = inst;
    const playing = mode !== "still";
    const bright = d.hl && d.hl[v] ? new Set(d.hl[v]) : null; // rows left undimmed, or null: nothing dims
    toks.forEach((t, i) => {
      const p = d.pos[i][v];
      const q = d.pos[i][prev];
      let role;
      if (p) {
        t.style.setProperty("--r", p[0]);
        t.style.setProperty("--c", p[1]);
        role = !playing ? "" : q ? " lt-mt-stay" : (d.mark && mode === "play" ? " lt-mt-in lt-mt-new" : " lt-mt-in");
      } else {
        role = playing && q ? " lt-mt-off lt-mt-out" : " lt-mt-off";
      }
      if (p && bright && bright.has(p[0])) role += " lt-mt-lit";
      t.className = unitClass(inst, i, v, role);
    });
    lns.forEach((n, r) => {
      const on = r < d.rows[v];
      const was = r < d.rows[prev];
      const lit = on && bright && bright.has(r) ? " lt-mt-lit" : "";
      n.className = `lt-morph-ln${on ? (playing && !was ? " lt-mt-in" : "") : (playing && was ? " lt-mt-off lt-mt-out" : " lt-mt-off")}${lit}`;
    });
    if (d.room === "fit") inst.stage.style.setProperty("--h", Math.max(1, d.rows[v]));
    if (inst.slots) {
      inst.box.classList.toggle("lt-morph-dim", !!bright);
      if (v !== prev || !inst.slots[inst.cur].classList.contains("lt-morph-hl-cur")) {
        // the other slot takes the new layer and fades in; the current one fades out
        const next = v === prev ? inst.cur : 1 - inst.cur;
        inst.slots[next].innerHTML = d.under[v];
        inst.slots[1 - next].classList.remove("lt-morph-hl-cur");
        inst.slots[next].classList.add("lt-morph-hl-cur");
        inst.cur = next;
      }
    }
  }

  // Bring the first changed row into view when the code overflows its box (as code-steps does).
  function reveal(inst, v, animate) {
    const pre = inst.pre;
    if (pre.scrollHeight <= pre.clientHeight + 1) return;
    const lh = parseFloat(getComputedStyle(pre).lineHeight) || 0;
    const box = pre.getBoundingClientRect();
    const scale = box.height / pre.offsetHeight || 1; // the slide may be scaled to the window
    const origin = (inst.stage.getBoundingClientRect().top - box.top) / scale + pre.scrollTop;
    const row = inst.d.hl && inst.d.hl[v] && inst.d.hl[v].length ? inst.d.hl[v][0] : inst.d.changed[v];
    const top = origin + row * lh - pre.clientHeight / 3;
    pre.scrollTo({ top: Math.max(0, top), behavior: animate ? "smooth" : "auto" });
  }

  Lattice.component("code-morph", {
    mount(el, data) {
      const box = el.querySelector(".lt-morph-box");
      const stage = el.querySelector(".lt-morph-stage");
      box.style.setProperty("--lt-md", `${data.duration}ms`);
      const toks = Array.from(el.querySelectorAll(".lt-mt"));
      const inst = { el, box, stage, toks, d: data, v: 0, prev: 0, until: 0,
        lns: Array.from(el.querySelectorAll(".lt-morph-ln")),
        cls: toks.map((t, i) => { const p = data.pos[i].find((x) => x); return p ? data.classes[p[2]] : ""; }),
        text: el.querySelector(".lt-morph-text"), label: el.querySelector(".lt-morph-label"), pre: el.querySelector("pre"),
        slots: data.hl ? Array.from(el.querySelectorAll(".lt-morph-hl")) : null, cur: 0 };
      stage.addEventListener("transitionend", (e) => { // room=fit: arrows follow the content below
        if (e.target === stage && e.propertyName === "height") relayout(inst, true);
      });
      return inst;
    },

    show(inst, position, info) {
      const v = Math.max(0, Math.min(position, inst.d.rows.length - 1));
      const now = performance.now();
      const animate = !!(info && info.animate) && inst.d.duration > 0 && v !== inst.v && !reduced();
      const mode = !animate ? "still" : now < inst.until ? "quick" : "play";
      inst.prev = inst.v;
      inst.v = v;
      inst.box.classList.remove("lt-morph-still", "lt-morph-play", "lt-morph-quick");
      inst.box.classList.add(`lt-morph-${mode}`);
      inst.box.style.setProperty("--lt-mq", `${Math.min(QUICK, inst.d.duration)}ms`);
      place(inst, v, mode);
      if (mode === "still") void inst.box.offsetWidth; // apply the final values with transitions off
      inst.until = mode === "play" ? now + inst.d.duration : mode === "quick" ? now + Math.min(QUICK, inst.d.duration) : 0;
      inst.text.innerHTML = inst.d.layers[v];
      if (inst.label) inst.label.textContent = inst.d.labels[v];
      reveal(inst, v, animate);
      const D = inst.d.duration;
      relayout(inst, animate, mode === "play" ? { delay: 0.2 * D, duration: 0.6 * D }
        : mode === "quick" ? { delay: 0, duration: Math.min(QUICK, D) } : null);
    },

    leave(inst) {
      // stop whatever is playing: the units jump to the values of the current version
      inst.box.classList.remove("lt-morph-play", "lt-morph-quick");
      inst.box.classList.add("lt-morph-still");
      inst.prev = inst.v;
      place(inst, inst.v, "still");
      void inst.box.offsetWidth;
      inst.until = 0;
    },
  });
})();
