// Animated graphs: layout computed at build time, one full state per position.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const STATES = ["default", "active", "frontier", "visited", "done", "path", "dim", "tree", "error"];
  let uid = 0;

  function svg(tag, attrs = {}, text) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    return e;
  }

  Lattice.component("graph-anim", {
    mount(el, data, api) {
      const L = data.layout;
      const id = `ga${++uid}`;
      const store = api.frames(data.frames);
      const root = el.querySelector(".lt-graph-anim");
      root.innerHTML = `<div class="lt-ga-main"><div class="lt-ga-canvas"></div><div class="lt-ga-panel" hidden></div></div><div class="lt-ga-caption"></div>`;
      const canvas = root.querySelector(".lt-ga-canvas");
      if (data.height) canvas.style.height = `${data.height}px`;
      const s = svg("svg", { viewBox: `0 0 ${L.width} ${L.height}`, class: "lt-ga-svg", preserveAspectRatio: "xMidYMid meet" });
      s.style.maxWidth = `${L.width * 1.7}px`;
      const defs = svg("defs");
      for (const st of STATES) {
        const m = svg("marker", { id: `${id}-${st}`, viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse", class: `lt-arrow st-${st}` });
        m.appendChild(svg("path", { d: "M0,0 L10,5 L0,10 z" }));
        defs.appendChild(m);
      }
      s.appendChild(defs);
      const gEdges = svg("g", { class: "lt-edges" });
      const gNodes = svg("g", { class: "lt-nodes" });
      s.append(gEdges, gNodes);
      const edges = {};
      for (const [key, e] of Object.entries(L.edges)) {
        const g = svg("g", { class: "lt-edge" });
        const path = svg("path", { d: e.path });
        g.appendChild(path);
        let text = null;
        if (e.lx != null) {
          text = svg("text", { x: e.lx, y: e.ly, class: "lt-edge-label", "text-anchor": "middle", "dominant-baseline": "middle" }, e.label || "");
          g.appendChild(text);
        }
        gEdges.appendChild(g);
        edges[key] = { g, path, text, base: e.label || "" };
      }
      const nodes = {};
      for (const [name, n] of Object.entries(L.nodes)) {
        const g = svg("g", { class: "lt-node", transform: `translate(${n.x},${n.y})` });
        const circle = svg("circle", { r: n.r });
        const text = svg("text", { class: "lt-node-name", "text-anchor": "middle", "dominant-baseline": "central" }, name);
        const badge = svg("text", { class: "lt-node-badge", "text-anchor": "middle", y: n.r + 15 });
        g.append(circle, text, badge);
        gNodes.appendChild(g);
        nodes[name] = { g, badge };
      }
      canvas.appendChild(s);
      return { id, L, store, nodes, edges, panel: root.querySelector(".lt-ga-panel"), caption: root.querySelector(".lt-ga-caption"), keys: data.panel };
    },

    show(inst, position, info) {
      const state = inst.store.at(position) || {};
      const ns = state.nodes || {};
      const es = state.edges || {};
      const root = inst.caption.parentElement;
      root.classList.toggle("lt-animate", !!info.animate);
      for (const [name, n] of Object.entries(inst.nodes)) {
        const st = ns[name] || {};
        n.g.setAttribute("class", `lt-node st-${st.state || "default"}${st.hidden ? " lt-gone" : ""}`);
        n.badge.textContent = st.label != null ? String(st.label) : "";
      }
      for (const [key, e] of Object.entries(inst.edges)) {
        let st = es[key];
        if (!st && !inst.L.directed) {
          const [u, v] = key.split("--");
          st = es[`${v}--${u}`];
        }
        st = st || {};
        const name = st.state || "default";
        e.g.setAttribute("class", `lt-edge st-${name}${st.hidden ? " lt-gone" : ""}`);
        if (inst.L.directed) e.path.setAttribute("marker-end", `url(#${inst.id}-${STATES.includes(name) ? name : "default"})`);
        if (e.text) e.text.textContent = st.label != null ? String(st.label) : e.base;
      }
      Lattice.renderPanel(inst.panel, state.panel, inst.keys);
      inst.caption.textContent = state.caption || "";
    },
  });
})();
