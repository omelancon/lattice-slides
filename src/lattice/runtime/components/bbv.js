// Basic block versioning: versions of a CFG appear, merge and vanish. Positions are computed at
// build time per frame (block bands); on a single step the nodes glide, any other move is immediate.
// Registers both bbv-anim (an algorithm run) and bbv-cfg (a source CFG, static or following a run).
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const DURATION = 380;
  const PAD_X = 10, PAD_Y = 6, LABEL_H = 22, LINE_H = 16;
  const STATES = ["default", "new", "gone", "active"];
  let uid = 0;

  function svg(tag, attrs = {}, text) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    return e;
  }

  // ---- rich text (spec 9.5): captions carry `kind:text` spans; context and code lines are split by
  // their own grammar. The same classes style HTML spans (caption, panel) and SVG tspans (nodes).
  const SPAN = /`(op|tag|v|var|ty|code|rm):([^`]*)`/g;
  const KEYWORDS = /(\b(?:if|goto|else|return|call|fail)\b|->|\[[^\]]*\])/;
  const TONES = { specialize: "active", "test kept": "active", test: "active", "test removed": "warn", merge: "warn",
    widen: "warn", "dead edge": "warn", fail: "warn", limit: "warn", done: "good", "fixed point": "good", exit: "good",
    reached: "accent", union: "accent", entry: "accent", "return points": "accent" };
  const esc = (t) => Lattice.esc(t);

  function plain(text) {
    return (text || "").replace(SPAN, (m, kind, body) => kind === "v" ? body.split("|")[0] : body);
  }

  // "fx | bg [0, 127]" -> [["ty", "fx | bg "], ["range", "[0, 127]"]]; a bound may be a vector length, "⟦x⟧-1", or "maxfix-1"
  function typeParts(text) {
    const m = /^(.*?)([\[({](?:[-−0-9∞^, ]|⟦[^⟧]*⟧|maxfix|minfix)*[\])}])$/.exec(text);
    if (!m) return [["ty", text]];
    return m[1] ? [["ty", m[1]], ["range", m[2]]] : [["range", m[2]]];
  }

  // "if pair?(lst) goto B else goto L" -> keywords and [i] indices marked
  function codeParts(text) {
    return text.split(KEYWORDS).filter((t) => t !== "").map((t) => [KEYWORDS.test(t) ? (t[0] === "[" ? "idx" : "kw") : "", t]);
  }

  function chip(inst, body) {
    const [label, block] = body.split("|");
    const color = inst.colors[block] || inst.colors[inst.byLabel[label]];
    return `<span class="lt-rc-v"${color ? ` style="--origin:${esc(color)}"` : ""}>${esc(label)}</span>`;
  }

  function richHTML(inst, text) {
    let html = "";
    let pos = 0;
    const part = (kind, body) => {
      if (kind === "op") return `<span class="lt-rc-op tone-${TONES[body] || "muted"}">${esc(body)}</span>`;
      if (kind === "tag") return `<span class="lt-rc-tag">${esc(body)}</span>`;
      if (kind === "v") return chip(inst, body);
      if (kind === "ty") return `<span class="lt-rc-ty">${typeParts(body).map(([c, t]) => c === "range" ? `<span class="lt-rc-range">${esc(t)}</span>` : esc(t)).join("")}</span>`;
      if (kind === "code" || kind === "rm") return `<span class="lt-rc-${kind}">${codeParts(body).map(([c, t]) => c ? `<span class="lt-rc-${c}">${esc(t)}</span>` : esc(t)).join("")}</span>`;
      return `<span class="lt-rc-${kind}">${esc(body)}</span>`;
    };
    for (const m of (text || "").matchAll(SPAN)) {
      if (m.index > pos) html += esc(text.slice(pos, m.index)).replaceAll(" · ", '<span class="lt-rc-sep"> · </span>');
      html += part(m[1], m[2]);
      pos = m.index + m[0].length;
    }
    if (pos < (text || "").length) html += esc(text.slice(pos)).replaceAll(" · ", '<span class="lt-rc-sep"> · </span>');
    return html;
  }

  function tspans(textEl, parts) {
    textEl.textContent = "";
    for (const [cls, t] of parts) {
      const ts = svg("tspan", cls ? { class: `lt-rc-${cls}` } : {}, t);
      textEl.appendChild(ts);
    }
  }

  // A context line ";; name: type", the name padded so that the types of a node line up
  function setContextLine(textEl, line, pad) {
    const i = line.indexOf(": ");
    if (i < 0) { tspans(textEl, [["", `;; ${line}`]]); return; }
    const name = line.slice(0, i), type = line.slice(i + 2);
    tspans(textEl, [["", ";; "], ["var", name + ":" + " ".repeat(Math.max(1, pad - name.length + 1))], ...typeParts(type)]);
  }

  function setContextLines(n, lines) {
    const pad = Math.max(0, ...lines.map((l) => { const i = l.indexOf(": "); return i < 0 ? 0 : i; }));
    n.ctxEls.forEach((t, i) => { if (i < lines.length) setContextLine(t, lines[i], pad); else t.textContent = ""; });
  }

  function node(inst, vid) {
    if (inst.nodes[vid]) return inst.nodes[vid];
    const v = inst.T.versions[vid];
    const [w, h] = inst.box.sizes[vid];
    const g = svg("g", { class: "lt-bbv-node" });
    const color = inst.colors[v.block];
    if (color) g.style.setProperty("--origin", color);
    g.appendChild(svg("rect", { width: w, height: h, rx: 8 }));
    const label = svg("text", { class: "lt-bbv-label", x: PAD_X, y: PAD_Y + 15 }, v.label);
    const star = svg("tspan", { class: "lt-bbv-star" }, "");
    label.appendChild(star);
    g.appendChild(label);
    let y = PAD_Y + LABEL_H + 12;
    const codeEls = [];
    const ctxEls = [];
    if (inst.show.includes("context")) {
      for (const line of v.context) {
        const t = svg("text", { class: "lt-bbv-ctx", x: PAD_X, y, "xml:space": "preserve" });
        g.appendChild(t);
        ctxEls.push(t);
        y += LINE_H;
      }
    }
    let ellipsis = null;
    if (inst.show.includes("code")) {
      ellipsis = svg("text", { class: "lt-bbv-code lt-bbv-ellipsis", x: PAD_X, y }, "…");
      g.appendChild(ellipsis);
      for (const c of v.code) {
        const t = svg("text", { class: `lt-bbv-code${c.removed ? " lt-bbv-removed" : ""}`, x: PAD_X, y, "xml:space": "preserve" });
        tspans(t, codeParts(c.text));
        g.appendChild(t);
        codeEls.push(t);
        y += LINE_H;
      }
    }
    const tip = [v.context.length ? `;; ${v.context.join("\n;; ")}` : "", ...v.code.map((c) => c.text)];
    if (v.after && v.after.length) tip.push("", `after: ${v.after.join(", ")}`);
    const title = svg("title", {}, tip.filter((s, i) => s !== "" || i > 0).join("\n"));
    g.appendChild(title);
    inst.gNodes.appendChild(g);
    // `origin` is remembered here: the class attribute is rewritten at every frame, including when
    // the node is hidden, so the colour must not depend on the classes the element currently has
    const n = (inst.nodes[vid] = { g, star, codeEls, ctxEls, ellipsis, title, w, h, v, origin: color ? " has-origin" : "" });
    setContextLines(n, v.context);
    return n;
  }

  function edge(inst, key) {
    if (inst.edges[key]) return inst.edges[key];
    const g = svg("g", { class: "lt-bbv-edge" });
    const path = svg("path", {});
    const label = svg("text", { class: "lt-bbv-edge-label", "text-anchor": "middle", "dominant-baseline": "middle" });
    g.append(path, label);
    inst.gEdges.appendChild(g);
    const [src, rest] = key.split("->");
    const [dst, kind] = rest.split(":");
    return (inst.edges[key] = { g, path, label, src, dst, kind });
  }

  function anchors(inst, at, e) {
    const a = at[e.src], b = at[e.dst];
    const na = inst.nodes[e.src], nb = inst.nodes[e.dst];
    if (!a || !b) return null;
    if (inst.box.direction === "LR") {
      return { sx: a[0] + na.w, sy: a[1] + na.h / 2, ex: b[0], ey: b[1] + nb.h / 2, back: b[0] < a[0] + na.w / 2 };
    }
    return { sx: a[0] + na.w / 2, sy: a[1] + na.h, ex: b[0] + nb.w / 2, ey: b[1], back: b[1] < a[1] + na.h / 2 };
  }

  // Rounded polyline through waypoints (for back edges, which travel along a lane beside the function).
  function polyline(points, r = 12) {
    let d = `M${points[0][0]},${points[0][1]}`;
    for (let i = 1; i < points.length - 1; i++) {
      const [px, py] = points[i - 1], [cx, cy] = points[i], [nx, ny] = points[i + 1];
      const d1 = Math.hypot(cx - px, cy - py), d2 = Math.hypot(nx - cx, ny - cy);
      const r1 = Math.min(r, d1 / 2), r2 = Math.min(r, d2 / 2);
      const ax = cx - (cx - px) / d1 * r1, ay = cy - (cy - py) / d1 * r1;
      const bx = cx + (nx - cx) / d2 * r2, by = cy + (ny - cy) / d2 * r2;
      d += ` L${ax},${ay} Q${cx},${cy} ${bx},${by}`;
    }
    const last = points[points.length - 1];
    d += ` L${last[0]},${last[1]}`;
    return d;
  }

  function route(inst, at, e) {
    const p = anchors(inst, at, e);
    if (!p) return null;
    const lr = inst.box.direction === "LR";
    if (!p.back) {
      const c1 = lr ? [p.sx + (p.ex - p.sx) / 2, p.sy] : [p.sx, p.sy + (p.ey - p.sy) / 2];
      const c2 = lr ? [p.sx + (p.ex - p.sx) / 2, p.ey] : [p.ex, p.ey - (p.ey - p.sy) / 2];
      const mid = [(p.sx + 3 * c1[0] + 3 * c2[0] + p.ex) / 8, (p.sy + 3 * c1[1] + 3 * c2[1] + p.ey) / 8];
      return { d: `M${p.sx},${p.sy} C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${p.ex},${p.ey}`, mid };
    }
    // a back edge leaves along the rank axis, travels on the lane beside the function and comes back in
    const band = inst.box.bands[inst.T.versions[e.src].function] || { lane: 0 };
    const lane = band.lane;
    const out = 22;
    let pts;
    if (lr) pts = [[p.sx, p.sy], [p.sx + out, p.sy], [p.sx + out, lane], [p.ex - out, lane], [p.ex - out, p.ey], [p.ex, p.ey]];
    else pts = [[p.sx, p.sy], [p.sx, p.sy + out], [lane, p.sy + out], [lane, p.ey - out], [p.ex, p.ey - out], [p.ex, p.ey]];
    const mid = lr ? [(p.sx + p.ex) / 2, lane] : [lane, (p.sy + p.ey) / 2];
    return { d: polyline(pts), mid };
  }

  function place(inst, at) {
    for (const [vid, p] of Object.entries(at)) if (inst.nodes[vid]) inst.nodes[vid].g.setAttribute("transform", `translate(${p[0]},${p[1]})`);
    for (const e of Object.values(inst.edges)) {
      if (e.g.classList.contains("lt-gone")) continue;
      const r = route(inst, at, e);
      if (!r) continue;
      e.path.setAttribute("d", r.d);
      e.label.setAttribute("x", r.mid[0]);
      e.label.setAttribute("y", r.mid[1]);
    }
  }

  // The caption lives in whatever space the drawing leaves: a long caption shrinks its text to fit
  // instead of pushing the drawing up (which rescaled it, since the canvas keeps its aspect ratio).
  function fitCaption(el) {
    el.style.fontSize = "";
    if (!el.clientHeight) return;  // hidden slide: fitted again by the observer when it shows
    const base = parseFloat(getComputedStyle(el).fontSize);
    let size = base;
    while (el.scrollHeight > el.clientHeight + 1 && size > base * 0.5) {
      size -= 1;
      el.style.fontSize = `${size}px`;
    }
  }

  function mount(el, data, api) {
    const root = el.querySelector(".lt-bbv-anim");
    root.innerHTML = `<div class="lt-ga-main"><div class="lt-ga-canvas"></div><div class="lt-ga-panel" hidden></div></div><div class="lt-ga-caption"></div>`;
    const canvas = root.querySelector(".lt-ga-canvas");
    if (data.height) canvas.style.height = `${data.height}px`;
    const box = data.box;
    const id = `bbv${++uid}`;
    const s = svg("svg", { viewBox: `0 0 ${box.width} ${box.height}`, class: "lt-ga-svg lt-bbv-svg", preserveAspectRatio: "xMidYMid meet" });
    s.style.maxWidth = `${box.width * 1.4}px`;
    const defs = svg("defs");
    for (const st of STATES) {
      const m = svg("marker", { id: `${id}-${st}`, viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse", class: `lt-arrow st-${st}` });
      m.appendChild(svg("path", { d: "M0,0 L10,5 L0,10 z" }));
      defs.appendChild(m);
    }
    s.appendChild(defs);
    const gHead = svg("g", { class: "lt-bbv-headers" });
    for (const [name, h] of Object.entries(box.headers || {})) {
      if (Object.keys(box.headers).length === 1 && data.static) continue;
      gHead.appendChild(svg("text", { class: "lt-bbv-header", x: h.x, y: h.y, "text-anchor": h.anchor, "dominant-baseline": "middle" }, name));
    }
    const gEdges = svg("g", { class: "lt-edges" });
    const gNodes = svg("g", { class: "lt-nodes" });
    s.append(gHead, gEdges, gNodes);
    canvas.appendChild(s);
    const caption = root.querySelector(".lt-ga-caption");
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(() => fitCaption(caption)).observe(caption);
    const byLabel = {};
    for (const v of Object.values(data.tables.versions)) if (!(v.label in byLabel)) byLabel[v.label] = v.block;
    return { id, root, box, T: data.tables, show: data.show, colors: data.colors || {}, byLabel, callEdges: !!data.callEdges,
      store: api.frames(data.frames), gEdges, gNodes, nodes: {}, edges: {}, at: {}, raf: 0, keys: data.panel || [],
      panel: root.querySelector(".lt-ga-panel"), caption, highlight: data.highlight };
  }

  function show(inst, position, info) {
    cancelAnimationFrame(inst.raf);
    const f = inst.store.at(position) || {};
    const pos = f.pos || {};
    const nodes = f.nodes || {};
    inst.root.classList.toggle("lt-animate", !!info.animate);
    const hl = inst.highlight ? inst.highlight[position] : null;
    for (const [vid, st] of Object.entries(nodes)) {
      const n = node(inst, vid);
      const mark = hl != null ? (vid === hl ? "active" : "none") : (st.mark || "none");
      n.g.setAttribute("class", `lt-bbv-node st-${st.state || "done"} mk-${mark}${n.origin}`);
      n.star.textContent = st.entry ? " ∗" : "";
      if (st.lines) {  // the context changes with the frame (abstract interpretation)
        setContextLines(n, st.lines);
        const tip = [`;; ${st.lines.join("\n;; ")}`, ...n.v.code.map((c) => c.text)];
        if (st.after && st.after.length) tip.push("", `after: ${st.after.join(", ")}`);
        n.title.textContent = tip.join("\n");
      }
      const queued = st.state === "queued";
      const shown = st.shown != null ? st.shown : n.codeEls.length;
      if (n.ellipsis) n.ellipsis.style.display = (queued || shown === 0) && n.codeEls.length ? "" : "none";
      n.codeEls.forEach((t, i) => { t.style.display = queued || i >= shown ? "none" : ""; });
    }
    for (const [vid, n] of Object.entries(inst.nodes)) if (!(vid in nodes)) n.g.setAttribute("class", `lt-bbv-node lt-gone${n.origin}`);
    const live = new Set();
    for (const [key, st] of Object.entries(f.edges || {})) {
      const e = edge(inst, key);
      if (e.kind === "call" && !inst.callEdges) continue;
      if (!(e.src in nodes) || !(e.dst in nodes)) continue;
      live.add(key);
      const state = st.state || "default";
      e.g.setAttribute("class", `lt-bbv-edge k-${e.kind} st-${state}`);
      e.path.setAttribute("marker-end", `url(#${inst.id}-${STATES.includes(state) ? state : "default"})`);
      e.label.textContent = st.label || (e.kind === "true" ? "#t" : e.kind === "false" ? "#f" : "");
    }
    for (const [key, e] of Object.entries(inst.edges)) if (!live.has(key)) e.g.setAttribute("class", "lt-bbv-edge lt-gone");
    const from = inst.at;
    inst.at = pos;
    const moves = info.animate && Object.keys(pos).some((k) => from[k] && (from[k][0] !== pos[k][0] || from[k][1] !== pos[k][1]));
    if (!moves) {
      place(inst, pos);
    } else {
      const start = Object.fromEntries(Object.keys(pos).map((n) => [n, from[n] || pos[n]]));
      const t0 = performance.now();
      const tick = (now) => {
        const k = Math.min(1, (now - t0) / DURATION);
        const ease = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        const at = {};
        for (const [n, p] of Object.entries(pos)) at[n] = [start[n][0] + (p[0] - start[n][0]) * ease, start[n][1] + (p[1] - start[n][1]) * ease];
        place(inst, at);
        if (k < 1) inst.raf = requestAnimationFrame(tick);
      };
      place(inst, start);
      inst.raf = requestAnimationFrame(tick);
    }
    renderPanel(inst, f.panel);
    inst.caption.innerHTML = richHTML(inst, f.caption || "");
    fitCaption(inst.caption);
  }

  // The panel of Lattice.renderPanel, with version labels as chips and the ∪ / ∇ steps of a
  // widening chain marked (abstract interpretation, spec 9.6)
  function renderPanel(inst, panel) {
    const el = inst.panel;
    const keys = inst.keys;
    const entries = Object.entries(panel || {}).filter(([k]) => keys.includes(k));
    entries.sort((a, b) => keys.indexOf(a[0]) - keys.indexOf(b[0]));
    el.hidden = entries.length === 0;
    const item = (x) => {
      const s = String(x);
      if (s in inst.byLabel) return chip(inst, `${s}|${inst.byLabel[s]}`);
      const m = /^([∪∇]) (.*)$/.exec(s);
      if (m) return `<span class="lt-rc-step ${m[1] === "∇" ? "tone-warn" : "tone-accent"}">${m[1]}</span> ${richHTML(inst, "`ty:" + m[2] + "`")}`;
      return esc(s);
    };
    el.innerHTML = entries.map(([k, v]) => {
      let body;
      if (Array.isArray(v)) body = `<div class="lt-pv-list lt-rc-list">${v.map((x) => `<span>${item(x)}</span>`).join("") || '<span class="lt-muted">empty</span>'}</div>`;
      else if (v && typeof v === "object") body = `<table class="lt-pv-map"><tr>${Object.keys(v).map((x) => `<th>${esc(x)}</th>`).join("")}</tr><tr>${Object.values(v).map((x) => `<td>${esc(x)}</td>`).join("")}</tr></table>`;
      else body = `<div class="lt-pv-scalar">${esc(v)}</div>`;
      return `<div class="lt-pv"><div class="lt-pv-name">${esc(k)}</div>${body}</div>`;
    }).join("");
  }

  function leave(inst) {
    cancelAnimationFrame(inst.raf);
    place(inst, inst.at);
  }

  Lattice.component("bbv-anim", { mount, show, leave });
  Lattice.component("bbv-cfg", { mount, show, leave });
  Lattice.component("abstract-interp-anim", { mount, show, leave });
})();
