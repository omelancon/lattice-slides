// Line highlighting for `code` (as a follower) and `code-steps`.
(() => {
  const controller = {
    mount(el, data) {
      const box = el.querySelector(".lt-code");
      const lines = new Map(Array.from(el.querySelectorAll(".lt-line")).map((l) => [Number(l.dataset.line), l]));
      return { box, lines, steps: (data && data.steps) || [[]], pre: el.querySelector("pre") };
    },
    show(inst, position) {
      const hl = new Set(inst.steps[position] || []);
      let first = null;
      for (const [n, line] of inst.lines) {
        const on = hl.has(n);
        line.classList.toggle("lt-hl", on);
        if (on && !first) first = line;
      }
      inst.box.classList.toggle("lt-has-hl", hl.size > 0);
      if (first && inst.pre.scrollHeight > inst.pre.clientHeight) {
        inst.pre.scrollTo({ top: first.offsetTop - inst.pre.clientHeight / 3, behavior: "smooth" });
      }
    },
  };
  Lattice.component("code", controller);
  Lattice.component("code-steps", controller);
})();
