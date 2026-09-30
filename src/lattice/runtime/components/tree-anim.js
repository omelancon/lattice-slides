// Animated trees: the shape changes between frames, positions are computed at build time per frame.
// On a single step the nodes glide from their old to their new places; any other move is immediate.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const DURATION = 380;

  function svg(tag, attrs = {}, text) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    return e;
  }

  function edgesOf(tree) {
    const out = [];
    for (const [p, kids] of Object.entries((tree && tree.kids) || {})) for (const c of kids) if (c != null) out.push([p, c]);
    return out;
  }

  // DOM elements are created the first time a node or an edge appears, then reused.
  function node(inst, name) {
    if (inst.nodes[name]) return inst.nodes[name];
    const r = inst.S.r;
    const g = svg("g", { class: "lt-node" });
    g.append(svg("circle", { r }),
      svg("text", { class: "lt-node-name", "text-anchor": "middle", "dominant-baseline": "central" }, name),
      svg("text", { class: "lt-node-badge lt-ta-badge", x: r * 0.95, y: -r * 0.95, "text-anchor": "start" }));
    inst.gNodes.appendChild(g);
    return (inst.nodes[name] = { g, badge: g.lastChild });
  }

  function edge(inst, key) {
    if (inst.edges[key]) return inst.edges[key];
    const g = svg("g", { class: "lt-edge" });
    const path = svg("path", {});
    g.appendChild(path);
    inst.gEdges.appendChild(g);
    return (inst.edges[key] = { g, path });
  }

  function place(inst, at, pairs) {
    for (const [name, p] of Object.entries(at)) inst.nodes[name].g.setAttribute("transform", `translate(${p[0]},${p[1]})`);
    for (const [u, v] of pairs) {
      const a = at[u];
      const b = at[v];
      if (a && b) inst.edges[`${u}->${v}`].path.setAttribute("d", `M${a[0]},${a[1]} L${b[0]},${b[1]}`);
    }
  }

  Lattice.component("tree-anim", {
    mount(el, data, api) {
      const root = el.querySelector(".lt-tree-anim");
      root.innerHTML = `<div class="lt-ga-main"><div class="lt-ga-canvas"></div><div class="lt-ga-panel" hidden></div></div><div class="lt-ga-caption"></div>`;
      const canvas = root.querySelector(".lt-ga-canvas");
      if (data.height) canvas.style.height = `${data.height}px`;
      const S = data.size;
      const s = svg("svg", { viewBox: `0 0 ${S.width} ${S.height}`, class: "lt-ga-svg", preserveAspectRatio: "xMidYMid meet" });
      s.style.maxWidth = `${S.width * 1.7}px`;
      const gEdges = svg("g", { class: "lt-edges" });
      const gNodes = svg("g", { class: "lt-nodes" });
      s.append(gEdges, gNodes);
      canvas.appendChild(s);
      return { root, S, store: api.frames(data.frames), gEdges, gNodes, nodes: {}, edges: {}, at: {}, pairs: [], raf: 0,
        keys: data.panel, panel: root.querySelector(".lt-ga-panel"), caption: root.querySelector(".lt-ga-caption") };
    },

    show(inst, position, info) {
      cancelAnimationFrame(inst.raf);
      const st = inst.store.at(position) || {};
      const pos = st.pos || {};
      const ns = st.nodes || {};
      const es = st.edges || {};
      const pairs = edgesOf(st.tree);
      inst.root.classList.toggle("lt-animate", !!info.animate);

      for (const name of Object.keys(pos)) {
        const n = node(inst, name);
        const s = ns[name] || {};
        n.g.setAttribute("class", `lt-node st-${s.state || "default"}${s.hidden ? " lt-gone" : ""}`);
        n.badge.textContent = s.label != null ? String(s.label) : "";
      }
      for (const [name, n] of Object.entries(inst.nodes)) if (!(name in pos)) n.g.setAttribute("class", "lt-node lt-ta-out");
      const live = new Set();
      for (const [u, v] of pairs) {
        const key = `${u}->${v}`;
        live.add(key);
        const s = es[key] || {};
        edge(inst, key).g.setAttribute("class", `lt-edge st-${s.state || "default"}${s.hidden ? " lt-gone" : ""}`);
      }
      for (const [key, e] of Object.entries(inst.edges)) if (!live.has(key)) e.g.setAttribute("class", "lt-edge lt-ta-out");

      const from = inst.at;
      inst.at = pos;
      inst.pairs = pairs;
      const moves = info.animate && Object.keys(pos).some((k) => from[k] && (from[k][0] !== pos[k][0] || from[k][1] !== pos[k][1]));
      if (!moves) {
        place(inst, pos, pairs);
      } else {
        const start = Object.fromEntries(Object.keys(pos).map((n) => [n, from[n] || pos[n]]));
        const t0 = performance.now();
        const tick = (now) => {
          const k = Math.min(1, (now - t0) / DURATION);
          const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
          const at = {};
          for (const [n, p] of Object.entries(pos)) at[n] = [start[n][0] + (p[0] - start[n][0]) * e, start[n][1] + (p[1] - start[n][1]) * e];
          place(inst, at, pairs);
          if (k < 1) inst.raf = requestAnimationFrame(tick);
        };
        place(inst, start, pairs);
        inst.raf = requestAnimationFrame(tick);
      }
      Lattice.renderPanel(inst.panel, st.panel, inst.keys);
      inst.caption.textContent = st.caption || "";
    },

    leave(inst) {
      cancelAnimationFrame(inst.raf);
      place(inst, inst.at, inst.pairs);
    },
  });
})();
