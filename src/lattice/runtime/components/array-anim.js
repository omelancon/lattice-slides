// Animated arrays: values as bars, persistent cell states, transient marks and pointers.
(() => {
  Lattice.component("array-anim", {
    mount(el, data, api) {
      const root = el.querySelector(".lt-array-anim");
      root.innerHTML = `<div class="lt-aa-main"><div class="lt-aa"><div class="lt-aa-row"></div><div class="lt-aa-ptr"></div></div><div class="lt-ga-panel" hidden></div></div><div class="lt-ga-caption"></div>`;
      const store = api.frames(data.frames);
      let max = 0;
      let numeric = true;
      for (let i = 0; i < store.count; i++) {
        for (const v of store.at(i).values || []) {
          if (typeof v === "number") max = Math.max(max, Math.abs(v));
          else numeric = false;
        }
      }
      return { root, store, max: max || 1, numeric, cells: [], keys: data.panel,
        row: root.querySelector(".lt-aa-row"), ptr: root.querySelector(".lt-aa-ptr"),
        panel: root.querySelector(".lt-ga-panel"), caption: root.querySelector(".lt-ga-caption") };
    },

    show(inst, position, info) {
      const st = inst.store.at(position) || {};
      const values = st.values || [];
      inst.root.classList.toggle("lt-animate", !!info.animate);
      if (inst.cells.length !== values.length) {
        inst.row.innerHTML = "";
        inst.cells = values.map((_, i) => {
          const c = document.createElement("div");
          c.className = "lt-cell";
          c.innerHTML = `${inst.numeric ? '<div class="lt-bar"></div>' : ""}<div class="lt-v"></div><div class="lt-i">${i}</div>`;
          inst.row.appendChild(c);
          return c;
        });
        inst.row.style.gridTemplateColumns = inst.ptr.style.gridTemplateColumns = `repeat(${values.length}, 1fr)`;
      }
      const cells = st.cells || {};
      const marks = st.marks || {};
      values.forEach((v, i) => {
        const c = inst.cells[i];
        const state = marks[i] || (cells[i] && (cells[i].state || cells[i])) || "default";
        c.className = `lt-cell st-${typeof state === "string" ? state : "default"}`;
        c.querySelector(".lt-v").textContent = v;
        const bar = c.querySelector(".lt-bar");
        if (bar) bar.style.height = `${Math.max(4, (Math.abs(v) / inst.max) * 100)}%`;
      });
      const byIndex = {};
      for (const [name, idx] of Object.entries(st.pointers || {})) {
        if (idx == null) continue;
        (byIndex[idx] ||= []).push(name);
      }
      inst.ptr.innerHTML = values.map((_, i) => `<div>${(byIndex[i] || []).map((n) => `<span>${Lattice.esc(n)}</span>`).join("")}</div>`).join("");
      Lattice.renderPanel(inst.panel, st.panel, inst.keys);
      inst.caption.textContent = st.caption || "";
    },
  });
})();
