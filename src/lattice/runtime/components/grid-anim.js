// Animated grids (mazes, dynamic programming tables): one SVG cell per position, optional row and
// column headers, persistent cell states, transient marks, pointers and arrows between cells.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const ARROWS = ["default", "active", "path", "dim"];
  let uid = 0;

  function svg(tag, attrs = {}, text) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    return e;
  }
  const stateOf = (v) => (v == null ? null : typeof v === "string" ? v : v.state || null);

  Lattice.component("grid-anim", {
    mount(el, data, api) {
      const root = el.querySelector(".lt-grid-anim");
      root.innerHTML = `<div class="lt-ga-main"><div class="lt-ga-canvas lt-gr-canvas"></div><div class="lt-ga-panel" hidden></div></div><div class="lt-ga-caption"></div>`;
      const canvas = root.querySelector(".lt-ga-canvas");
      if (data.height) canvas.style.height = `${data.height}px`;
      const D = data.dims;
      const c = D.cell;
      const pad = 6;
      const x0 = pad + (D.rowHead ? c * 1.1 : 0);
      const y0 = pad + (D.colHead ? c * 0.8 : 0);
      const W = x0 + D.cols * c + pad;
      const H = y0 + D.rows * c + pad;
      const id = `gr${++uid}`;
      const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "lt-ga-svg lt-gr-svg", preserveAspectRatio: "xMidYMid meet" });
      s.style.maxWidth = `${W * 1.6}px`;
      s.style.fontSize = `${c * 0.42}px`;
      const defs = svg("defs");
      for (const st of ARROWS) {
        const m = svg("marker", { id: `${id}-${st}`, viewBox: "0 0 10 10", refX: "8", refY: "5", markerWidth: "3.4", markerHeight: "3.4", orient: "auto-start-reverse", class: `lt-gr-head st-${st}` });
        m.appendChild(svg("path", { d: "M0,0 L10,5 L0,10 z" }));
        defs.appendChild(m);
      }
      s.appendChild(defs);
      const gCells = svg("g", { class: "lt-gr-cells" });
      const gHeads = svg("g", { class: "lt-gr-heads" });
      const gArrows = svg("g", { class: "lt-gr-arrows" });
      const gPtrs = svg("g", { class: "lt-gr-ptrs" });
      s.append(gCells, gHeads, gArrows, gPtrs);
      const cells = [];
      for (let r = 0; r < D.rows; r++) {
        const row = [];
        for (let k = 0; k < D.cols; k++) {
          const g = svg("g", { class: "lt-gc", transform: `translate(${x0 + k * c},${y0 + r * c})` });
          g.append(svg("rect", { width: c, height: c }), svg("text", { x: c / 2, y: c / 2, "text-anchor": "middle", "dominant-baseline": "central" }));
          gCells.appendChild(g);
          row.push({ g, text: g.lastChild });
        }
        cells.push(row);
      }
      const rowHeads = [];
      const colHeads = [];
      if (D.rowHead) for (let r = 0; r < D.rows; r++) rowHeads.push(gHeads.appendChild(svg("text", { x: x0 - c * 0.25, y: y0 + r * c + c / 2, "text-anchor": "end", "dominant-baseline": "central" })));
      if (D.colHead) for (let k = 0; k < D.cols; k++) colHeads.push(gHeads.appendChild(svg("text", { x: x0 + k * c + c / 2, y: y0 - c * 0.3, "text-anchor": "middle" })));
      canvas.appendChild(s);
      const center = (key) => {
        const [r, k] = key.split(",").map(Number);
        return [x0 + k * c + c / 2, y0 + r * c + c / 2];
      };
      return { root, id, c, center, cells, rowHeads, colHeads, gArrows, gPtrs, store: api.frames(data.frames),
        keys: data.panel, panel: root.querySelector(".lt-ga-panel"), caption: root.querySelector(".lt-ga-caption") };
    },

    show(inst, position, info) {
      const st = inst.store.at(position) || {};
      const values = st.values || [];
      const cs = st.cells || {};
      const marks = st.marks || {};
      inst.root.classList.toggle("lt-animate", !!info.animate);
      inst.cells.forEach((row, r) => row.forEach((cell, k) => {
        const inside = r < values.length && k < (values[r] || []).length;
        const key = `${r},${k}`;
        const state = stateOf(marks[key]) || stateOf(cs[key]) || "default";
        cell.g.setAttribute("class", inside ? `lt-gc st-${state}` : "lt-gc lt-gc-out");
        const v = inside ? values[r][k] : null;
        cell.text.textContent = v == null ? "" : String(v);
      }));
      inst.rowHeads.forEach((t, r) => { t.textContent = st.rows && st.rows[r] != null ? String(st.rows[r]) : ""; });
      inst.colHeads.forEach((t, k) => { t.textContent = st.cols && st.cols[k] != null ? String(st.cols[k]) : ""; });

      const c = inst.c;
      inst.gArrows.innerHTML = "";
      for (const [key, val] of Object.entries(st.arrows || {})) {
        const [a, b] = key.split("->");
        if (!a || !b) continue;
        const [x1, y1] = inst.center(a);
        const [x2, y2] = inst.center(b);
        const len = Math.hypot(x2 - x1, y2 - y1) || 1;
        const cut = c * 0.28;
        const [ux, uy] = [(x2 - x1) / len, (y2 - y1) / len];
        const name = stateOf(val) || "default";
        const g = svg("g", { class: `lt-gr-arrow st-${name}` });
        g.appendChild(svg("path", { d: `M${x1 + ux * cut},${y1 + uy * cut} L${x2 - ux * cut},${y2 - uy * cut}`,
          "marker-end": `url(#${inst.id}-${ARROWS.includes(name) ? name : "default"})` }));
        inst.gArrows.appendChild(g);
      }
      inst.gPtrs.innerHTML = "";
      const byCell = {};
      for (const [name, rc] of Object.entries(st.pointers || {})) if (rc) (byCell[`${rc[0]},${rc[1]}`] ||= []).push(name);
      for (const [key, names] of Object.entries(byCell)) {
        const [x, y] = inst.center(key);
        const g = svg("g", { class: "lt-gr-ptr" });
        g.append(svg("rect", { x: x - c / 2 + 2, y: y - c / 2 + 2, width: c - 4, height: c - 4, rx: 4 }),
          svg("text", { x: x - c / 2 + 4, y: y - c / 2 + 3, "dominant-baseline": "hanging" }, names.join(",")));
        inst.gPtrs.appendChild(g);
      }
      Lattice.renderPanel(inst.panel, st.panel, inst.keys);
      inst.caption.textContent = st.caption || "";
    },
  });
})();
