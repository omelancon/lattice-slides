// Show one version per position; the Python side already marked the changes.
Lattice.component("diff-steps", {
  mount(el) {
    return { panes: Array.from(el.querySelectorAll(".lt-diff-pane")) };
  },
  show(inst, position) {
    inst.panes.forEach((p, i) => { p.hidden = i !== position; });
  },
});
