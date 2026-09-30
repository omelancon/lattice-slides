// Runtime for the `call-stack` component: draws the stack of calls, newest on top.
Lattice.component("call-stack", {
  mount(el, data, api) {
    const root = el.querySelector(".call-stack");
    root.innerHTML = '<ol class="cs-frames"></ol><p class="cs-caption"></p>';
    return { store: api.frames(data.frames), list: root.querySelector("ol"), caption: root.querySelector("p") };
  },
  show(inst, position) {
    const state = inst.store.at(position);
    const frames = state.stack || [];
    inst.list.innerHTML = frames
      .map((f, i) => `<li class="${i === frames.length - 1 ? "top" : ""} ${f.ret != null ? "ret" : ""}">` +
        `<code>${Lattice.esc(f.call)}</code><span>${f.ret != null ? "returns " + Lattice.esc(f.ret) : Lattice.esc(f.note || "")}</span></li>`)
      .reverse()
      .join("");
    inst.caption.textContent = state.caption || "";
  },
});
