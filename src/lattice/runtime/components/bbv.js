// Basic block versioning: versions of a CFG appear, merge and vanish. Positions are computed at
// build time per frame (block bands); on a single step the nodes glide, any other move is immediate.
// Registers bbv-anim (an algorithm run), bbv-cfg (a source CFG, static or following a run),
// abstract-interp-anim and bbv-merge (a merge heuristic at work: contexts merged two by two).
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const DURATION = 380;
  const MERGE_GLIDE = 650;  // bbv-merge: the pair meeting, and the contexts going back to the layout
  const PAD_X = 10, PAD_Y = 6, LABEL_H = 22, LINE_H = 16;
  const AFTER_HEAD = ";; after:";  // as layout.AFTER_HEAD, which sizes the enlarged block
  const ZOOM_PAD = 6;  // room around an enlarged block for its outline
  const MARK_CH = 7.3, MARK_PAD = 3, MARK_H = 15;  // the box of an edge label: 12px monospace characters
  const STATES = ["default", "new", "gone", "active", "path", "dim"];
  // arrowheads in drawing units, whatever the width of the edge: [length, width], larger for a lit edge
  const ARROW = [10, 7], ARROW_LIT = [12, 9], LIT = ["new", "active", "path"];
  // every edge ends with a straight leg at least this long, so that its arrowhead (whose back lies 0.9 of its
  // length before the end) sits on it, aligned with the edge; shorter only where the gap it ends in is
  const LEG = 13;
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
    "closest pair": "warn", "random pair": "warn", widen: "warn", "dead edge": "warn", fail: "warn", limit: "warn",
    done: "good", "fixed point": "good", exit: "good",
    reached: "accent", union: "accent", entry: "accent", "return points": "accent", path: "good",
    "no side effect": "good", "constant result": "accent", "constant fold": "good" };
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

  function setLines(els, lines) {
    const pad = Math.max(0, ...lines.map((l) => { const i = l.indexOf(": "); return i < 0 ? 0 : i; }));
    els.forEach((t, i) => { if (i < lines.length) setContextLine(t, lines[i], pad); else t.textContent = ""; });
  }

  function setContextLines(n, lines) {
    setLines(n.ctxEls, lines);
  }

  // Draws a node: its box, label, context lines (`show` has "context"), code lines ("code") and, in an
  // enlarged block, its exit context under a heading ("after"; spec 9.5). `ctx` and `after` are the
  // lines to make room for: the slots of the drawing, or the lines of the current frame in a zoom.
  function drawNode(inst, v, show, [w, h], ctx, after, tooltip) {
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
    const afterEls = [];
    if (show.includes("context")) {
      for (let i = 0; i < ctx.length; i++) {
        const t = svg("text", { class: "lt-bbv-ctx", x: PAD_X, y, "xml:space": "preserve" });
        g.appendChild(t);
        ctxEls.push(t);
        y += LINE_H;
      }
    }
    let ellipsis = null;
    const altEls = [];
    if (show.includes("code")) {
      ellipsis = svg("text", { class: "lt-bbv-code lt-bbv-ellipsis", x: PAD_X, y }, "…");
      g.appendChild(ellipsis);
      // a call site folded by ΛV (spec 9.5) also draws its code before the fold, in the same place: a
      // frame shows one or the other (`alt`), and the box has room for the longer one
      const lines = (code, els) => code.map((c, i) => {
        const t = svg("text", { class: `lt-bbv-code${c.removed ? " lt-bbv-removed" : ""}`, x: PAD_X, y: y + i * LINE_H, "xml:space": "preserve" });
        tspans(t, codeParts(c.text));
        g.appendChild(t);
        els.push(t);
      });
      lines(v.code, codeEls);
      lines(v.alt || [], altEls);
      y += Math.max(v.code.length, (v.alt || []).length) * LINE_H;
    }
    if (show.includes("after") && after.length) {
      const head = svg("text", { class: "lt-bbv-ctx lt-bbv-after-head", x: PAD_X, y, "xml:space": "preserve" }, AFTER_HEAD);
      g.appendChild(head);
      afterEls.push(head);
      y += LINE_H;
      for (let i = 0; i < after.length; i++) {
        const t = svg("text", { class: "lt-bbv-ctx lt-bbv-after", x: PAD_X, y, "xml:space": "preserve" });
        g.appendChild(t);
        afterEls.push(t);
        y += LINE_H;
      }
    }
    let title = null;
    if (tooltip) {
      const tip = [v.context.length ? `;; ${v.context.join("\n;; ")}` : "", ...v.code.map((c) => c.text)];
      if (v.after && v.after.length) tip.push("", `after: ${v.after.join(", ")}`);
      title = svg("title", {}, tip.filter((s, i) => s !== "" || i > 0).join("\n"));
      g.appendChild(title);
    }
    // `origin` is remembered here: the class attribute is rewritten at every frame, including when
    // the node is hidden, so the colour must not depend on the classes the element currently has
    const n = { g, star, codeEls, altEls, ctxEls, afterEls, ellipsis, title, w, h, v, origin: color ? " has-origin" : "" };
    setContextLines(n, ctx);
    if (afterEls.length) setLines(afterEls.slice(1), after);
    return n;
  }

  function node(inst, vid) {
    if (inst.nodes[vid]) return inst.nodes[vid];
    const v = inst.T.versions[vid];
    const n = drawNode(inst, v, inst.show, inst.box.sizes[vid], v.context, [], true);
    n.g.dataset.vid = vid;
    inst.gNodes.appendChild(n.g);
    return (inst.nodes[vid] = n);
  }

  // The state of a node in a frame: classes, entry star, the context of the frame (abstract
  // interpretation), the code specialized so far, and the exit context once the block is done.
  function nodeState(inst, n, vid, st, position) {
    // a follower highlights the block of the frame, or every block of a path frame (spec 9.5)
    const hl = inst.highlight ? inst.highlight[position] : null;
    const mark = Array.isArray(hl) ? (hl.includes(vid) ? "path" : "none")
      : hl != null ? (vid === hl ? "active" : "none") : (st.mark || "none");
    n.g.setAttribute("class", `lt-bbv-node st-${st.state || "done"} mk-${mark}${n.origin}`);
    n.star.textContent = st.entry ? " ∗" : "";
    if (st.lines) {  // the context changes with the frame (abstract interpretation)
      setContextLines(n, st.lines);
      if (n.title) {
        const tip = [`;; ${st.lines.join("\n;; ")}`, ...n.v.code.map((c) => c.text)];
        if (st.after && st.after.length) tip.push("", `after: ${st.after.join(", ")}`);
        n.title.textContent = tip.join("\n");
      }
    }
    const queued = st.state === "queued";
    // before its fold, a folded call site shows the code it had then (`alt`)
    const alt = !!st.alt && n.altEls.length > 0;
    const els = alt ? n.altEls : n.codeEls;
    (alt ? n.codeEls : n.altEls).forEach((t) => { t.style.display = "none"; });
    const shown = st.shown != null ? st.shown : els.length;
    if (n.ellipsis) n.ellipsis.style.display = (queued || shown === 0) && els.length ? "" : "none";
    els.forEach((t, i) => { t.style.display = queued || i >= shown ? "none" : ""; });
    if (n.title && !st.lines && n.altEls.length) {  // the tooltip of a folded call site follows its code
      const tip = [n.v.context.length ? `;; ${n.v.context.join("\n;; ")}` : "", ...(alt ? n.v.alt : n.v.code).map((c) => c.text)];
      if (n.v.after && n.v.after.length) tip.push("", `after: ${n.v.after.join(", ")}`);
      n.title.textContent = tip.filter((s, i) => s !== "" || i > 0).join("\n");
    }
    // the exit context is known once the version is specialized to its end
    const finished = !queued && shown >= els.length;
    n.afterEls.forEach((t) => { t.style.display = finished ? "" : "none"; });
  }

  // The text of an edge label. On a path frame, a return edge names the return point indices the path
  // took (`lit`, spec 9.5): those are drawn in the path's colour and the label's other indices fade.
  // The text is the same either way, so the label's mark keeps its size.
  function edgeLabel(el, text, lit) {
    if (!lit || !lit.length) { el.textContent = text; return; }
    el.textContent = "";
    text.split(" ").forEach((tok, i) => {
      if (i) el.appendChild(document.createTextNode(" "));
      const m = /^\[(\d+)\]$/.exec(tok);
      const on = m && lit.includes(Number(m[1]));
      el.appendChild(svg("tspan", { class: on ? "lt-bbv-edge-lit" : "lt-bbv-edge-unlit" }, tok));
    });
  }

  // An edge: its path, its label at the middle of the curve, and the mark an arrow at the edge measures
  // (spec 9.5): invisible, at the middle of the curve, covering the label when there is one.
  function edge(inst, key) {
    if (inst.edges[key]) return inst.edges[key];
    const g = svg("g", { class: "lt-bbv-edge", "data-key": key });
    const path = svg("path", {});
    const label = svg("text", { class: "lt-bbv-edge-label", "text-anchor": "middle", "dominant-baseline": "middle" });
    const mark = svg("rect", { class: "lt-bbv-edge-mark", width: 0, height: 0 });
    g.append(path, label, mark);
    inst.gEdges.appendChild(g);
    const [src, rest] = key.split("->");
    const [dst, kind] = rest.split(":");
    return (inst.edges[key] = { g, path, label, mark, src, dst, kind, chars: 0 });
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

  // Rounded polyline through waypoints (for back edges, which travel along a lane beside the function). The
  // last corner is rounded only as much as leaves a straight leg of LEG under the arrowhead (a sharp corner when
  // the last segment is shorter).
  function polyline(points, r = 12) {
    let d = `M${points[0][0]},${points[0][1]}`;
    const lastCorner = points.length - 2;
    for (let i = 1; i < points.length - 1; i++) {
      const [px, py] = points[i - 1], [cx, cy] = points[i], [nx, ny] = points[i + 1];
      const d1 = Math.hypot(cx - px, cy - py), d2 = Math.hypot(nx - cx, ny - cy);
      // the last corner keeps the leg straight, and stays round (as wide on both sides)
      const r2 = Math.min(r, i === lastCorner ? Math.max(0, d2 - LEG) : d2 / 2);
      const r1 = i === lastCorner ? Math.min(r2, d1 / 2) : Math.min(r, d1 / 2);
      const ax = cx - (cx - px) / d1 * r1, ay = cy - (cy - py) / d1 * r1;
      const bx = cx + (nx - cx) / d2 * r2, by = cy + (ny - cy) / d2 * r2;
      d += ` L${ax},${ay} Q${cx},${cy} ${bx},${by}`;
    }
    const last = points[points.length - 1];
    d += ` L${last[0]},${last[1]}`;
    return d;
  }

  // Edges between the same two nodes (the two outcomes of `if x goto L else goto L`) are drawn side by side:
  // `side` is -1, 0 or 1 (0 for a lone edge), across the direction of the drawing.
  const PARALLEL_END = 8, PARALLEL_BEND = 26, PARALLEL_LANE = 10;

  function route(inst, at, e, side = 0) {
    const p = anchors(inst, at, e);
    if (!p) return null;
    const lr = inst.box.direction === "LR";
    if (side) {  // ends apart across the rank axis, so that both arrowheads show
      if (lr) { p.sy += side * PARALLEL_END; p.ey += side * PARALLEL_END; }
      else { p.sx += side * PARALLEL_END; p.ex += side * PARALLEL_END; }
    }
    if (!p.back) {  // a curve, then the straight leg under the arrowhead
      const bend = side * PARALLEL_BEND;
      const lead = Math.min(LEG, Math.max(0, (lr ? p.ex - p.sx : p.ey - p.sy) / 2));
      const qx = lr ? p.ex - lead : p.ex, qy = lr ? p.ey : p.ey - lead;
      const c1 = lr ? [p.sx + (qx - p.sx) / 2, p.sy + bend] : [p.sx + bend, p.sy + (qy - p.sy) / 2];
      const c2 = lr ? [p.sx + (qx - p.sx) / 2, qy + bend] : [qx + bend, qy - (qy - p.sy) / 2];
      const mid = [(p.sx + 3 * c1[0] + 3 * c2[0] + qx) / 8, (p.sy + 3 * c1[1] + 3 * c2[1] + qy) / 8];
      return { d: `M${p.sx},${p.sy} C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${qx},${qy} L${p.ex},${p.ey}`, mid };
    }
    // a back edge leaves along the rank axis, travels on the lane beside the function and comes back in
    const band = inst.box.bands[inst.T.versions[e.src].function] || { lane: 0 };
    // parallel back edges nest without crossing: the one whose ends lie toward the lane takes the inner lane
    // and leaves and enters closer to its nodes
    const toward = side * Math.sign(band.lane - (lr ? p.sy : p.sx));
    const lane = band.lane - side * PARALLEL_LANE;
    const out = 22 - toward * PARALLEL_LANE * 0.6;
    let pts;
    if (lr) pts = [[p.sx, p.sy], [p.sx + out, p.sy], [p.sx + out, lane], [p.ex - out, lane], [p.ex - out, p.ey], [p.ex, p.ey]];
    else pts = [[p.sx, p.sy], [p.sx, p.sy + out], [lane, p.sy + out], [lane, p.ey - out], [p.ex, p.ey - out], [p.ex, p.ey]];
    const mid = lr ? [(p.sx + p.ex) / 2, lane] : [lane, (p.sy + p.ey) / 2];
    return { d: polyline(pts), mid };
  }

  // ---- bands of ranks (spec 9.5): the ranks of a function cut into bands laid side by side. Edges are routed
  // in the frame of the drawing: `a` across (the rank axis: y in TB, x in LR), `l` along (the packing axis).
  const EXIT_RANK = 0.35, EXIT_LINE = 0.35;  // where an edge runs in the gap after a rank or a line, as a fraction of it
  const ENTRY_LONE = 0.46;  // where a lone edge runs in the gap before the rank or line it enters (room for its leg)
  // the runs of several edges in one such gap take slots of their own, in this part of the gap (fractions of it,
  // from the rank or line they leave or reach), at most SLOT_STEP apart: the runs into a node lie farther from it
  // than those out of one, so that the straight leg under an arrowhead fits, and the two parts never overlap
  const SLOT_OUT = [0.06, 0.38], SLOT_IN = [0.3, 0.62], SLOT_STEP = 5;
  const LABEL_AFTER = 20;  // the label of an edge between bands: this far along its run toward the gutter, at most
  const LANE = 18;  // as layout.LANE: the first lane of a gutter, from the band it borders
  const GUTTER_LANES = 5;  // as layout.GUTTER_LANES: the most lanes of the edges between bands in a gutter

  // The bands, gutters and ranks of a function whose edges travel in gutters (spec 9.5): its bands of ranks, or
  // a function without bands that has loops (one band, with its head and tail gutters); null otherwise
  function layoutOf(inst, fn) {
    const cache = (inst.layouts ||= {});
    if (fn in cache) return cache[fn];
    const rw = inst.box.rankWrap && inst.box.rankWrap[fn];
    const b = inst.box.bands[fn] || {};
    let out = null;
    if (rw) out = { ...rw, head: b.head, tail: b.tail };
    else if (b.blocks) out = { bands: [{ start: b.start, end: b.end, flip: false }], gutters: [], blocks: b.blocks, head: b.head, tail: b.tail };
    return (cache[fn] = out);
  }

  function banded(inst, e) {
    const rw = inst.box.rankWrap;
    if (!rw) return null;
    const fa = inst.T.versions[e.src].function, fb = inst.T.versions[e.dst].function;
    return fa === fb && rw[fa] ? rw[fa] : null;
  }

  // A node in the frame of the drawing: across start and size, along start and size
  function frameBox(inst, at, vid) {
    const p = at[vid], n = inst.nodes[vid];
    if (!p || !n) return null;
    return inst.box.direction === "LR" ? { a: p[0], as: n.w, l: p[1], ls: n.h } : { a: p[1], as: n.h, l: p[0], ls: n.w };
  }

  function pt(inst, a, l) {
    return inst.box.direction === "LR" ? [a, l] : [l, a];
  }

  // The free gaps before and after the line of every node of a banded function (between two lines of a wrapped
  // rank, or before and after the rank), read from the positions: an edge between bands runs along them.
  function lineGaps(inst, at) {
    const gapRank = inst.box.gaps.rank, gapLine = inst.box.gaps.line;
    const nodes = (inst.frame && inst.frame.nodes) || {};
    const ranks = {};
    for (const vid of Object.keys(at)) {
      const v = inst.T.versions[vid];
      const fw = v && layoutOf(inst, v.function);
      if (!fw || !inst.nodes[vid] || (nodes[vid] && nodes[vid].mark === "gone")) continue;
      const b = frameBox(inst, at, vid);
      const key = `${v.function}/${fw.blocks[v.name][1]}`;
      const lines = (ranks[key] ||= []);
      let line = lines.find((x) => Math.abs(x.start - b.a) < 0.5);
      if (!line) lines.push((line = { start: b.a, end: b.a + b.as }));
      line.end = Math.max(line.end, b.a + b.as);
    }
    for (const lines of Object.values(ranks)) lines.sort((x, y) => x.start - y.start);
    return (vid) => {
      const v = inst.T.versions[vid];
      const fw = layoutOf(inst, v.function);
      const [, rank, start, end] = fw.blocks[v.name];
      const lines = ranks[`${v.function}/${rank}`] || [];
      const b = frameBox(inst, at, vid);
      const i = b ? lines.findIndex((x) => Math.abs(x.start - b.a) < 0.5) : -1;
      // a gap: the edge of the line or rank it borders, its width, which way it lies, where a lone run goes
      const gap = (at, room, dir, frac) => ({ at, room, dir, mid: at + dir * frac * room });
      if (i < 0) return { before: gap(start, gapRank, -1, EXIT_RANK), after: gap(end, gapRank, 1, EXIT_RANK) };
      return { before: i === 0 ? gap(start, gapRank, -1, EXIT_RANK) : gap(lines[i].start, gapLine, -1, EXIT_LINE),
        after: i === lines.length - 1 ? gap(end, gapRank, 1, EXIT_RANK) : gap(lines[i].end, gapLine, 1, EXIT_LINE) };
    };
  }

  // An edge inside one band: as without bands, along the band's own direction (a band running backwards
  // swaps the sides of its nodes), its back edges on the band's lane
  function routeInBand(inst, at, e, side, fw) {
    const A = frameBox(inst, at, e.src), B = frameBox(inst, at, e.dst);
    if (!A || !B) return null;
    const band = fw.bands[fw.blocks[inst.T.versions[e.src].name][0]];
    const s = band.flip ? -1 : 1;
    let sa = s > 0 ? A.a + A.as : A.a, ea = s > 0 ? B.a : B.a + B.as;
    let sl = A.l + A.ls / 2, el = B.l + B.ls / 2;
    if (side) { sl += side * PARALLEL_END; el += side * PARALLEL_END; }
    const back = s > 0 ? B.a < A.a + A.as / 2 : B.a + B.as > A.a + A.as / 2;
    if (!back) {  // a curve, then the straight leg under the arrowhead
      const qa = ea - s * Math.min(LEG, Math.max(0, s * (ea - sa) / 2));
      const bend = side * PARALLEL_BEND, ma = sa + (qa - sa) / 2;
      const p0 = pt(inst, sa, sl), c1 = pt(inst, ma, sl + bend), c2 = pt(inst, ma, el + bend), p3 = pt(inst, qa, el);
      const end = pt(inst, ea, el);
      const mid = [(p0[0] + 3 * c1[0] + 3 * c2[0] + p3[0]) / 8, (p0[1] + 3 * c1[1] + 3 * c2[1] + p3[1]) / 8];
      return { d: `M${p0[0]},${p0[1]} C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${p3[0]},${p3[1]} L${end[0]},${end[1]}`, mid };
    }
    // a back edge here only while nodes glide (a loop of the frame travels in a gutter): on a lane after the band
    const bandLane = band.end + LANE;
    const toward = side * Math.sign(bandLane - sl);
    const lane = bandLane - side * PARALLEL_LANE;
    const out = 22 - toward * PARALLEL_LANE * 0.6;
    const pts = [[sa, sl], [sa + s * out, sl], [sa + s * out, lane], [ea - s * out, lane], [ea - s * out, el], [ea, el]];
    return { d: polyline(pts.map(([a, l]) => pt(inst, a, l))), mid: pt(inst, (sa + ea) / 2, lane) };
  }

  // The course of an edge between two bands, in the frame of the drawing, before its gutter lanes are known:
  // its ends, the gaps it runs along, its gutters (forward edges use the gutter after their band, backward
  // ones the gutter before it) and, across bands in between, the end of the ranks it passes by.
  function course(inst, at, e, side, fw, gaps) {
    const A = frameBox(inst, at, e.src), B = frameBox(inst, at, e.dst);
    if (!A || !B) return null;
    const bs = fw.blocks[inst.T.versions[e.src].name][0], bd = fw.blocks[inst.T.versions[e.dst].name][0];
    const fs = fw.bands[bs].flip, fd = fw.bands[bd].flip;
    const gs = gaps(e.src), gd = gaps(e.dst);
    const exitGap = fs ? gs.before : gs.after, entryGap = fd ? gd.after : gd.before;
    const c = {
      x0: [fs ? A.a : A.a + A.as, A.l + A.ls / 2 + side * PARALLEL_END],
      exitGap, exitA: exitGap.mid,
      y0: [fd ? B.a + B.as : B.a, B.l + B.ls / 2 + side * PARALLEL_END],
      entryGap, entryA: entryGap.at + entryGap.dir * ENTRY_LONE * entryGap.room,
      gOut: bd > bs ? bs : bs - 1, gIn: bd > bs ? bd - 1 : bd, right: bd > bs, side,
    };
    if (c.gOut !== c.gIn) {
      const via = (t) => Math.abs(c.exitA - t) + Math.abs(c.entryA - t);
      c.endA = via(fw.top) <= via(fw.bottom) ? fw.top : fw.bottom;
    }
    return c;
  }

  // Lanes of the gutters (spec 9.5). A gutter between bands g and g+1 holds four groups, from band g: the loops of
  // band g (`near`), the edges from band g on (`x`, right), the edges toward band g (`x`, left), the loops of band
  // g+1 (`far`); a head or tail gutter holds the loops of the band it borders (`near`), its lanes going outward.
  // Every target has its own lane in a group. Loops nest: the shortest nearest their band. Edges between bands:
  // the edges that travel farthest nearest the band they leave; beyond the lanes left to them (at most
  // GUTTER_LANES), the targets closest to each other share one.
  function assignLanes(fw, uses) {
    const lanes = {};
    for (const [g, list] of Object.entries(uses)) {
      const gut = g === "head" ? fw.head : g === "tail" ? fw.tail : fw.gutters[g];
      if (!gut) continue;
      const groups = {};
      for (const u of list) {
        const id = `${u.group}/${u.target}`;
        const x = (groups[id] ||= { id, group: u.group, target: u.target, right: u.right, from: u.from, to: u.to, n: 0, span: 0 });
        x.from = (x.from * x.n + u.from) / (x.n + 1);
        x.n += 1;
        x.span = Math.max(x.span, Math.abs(u.to - u.from));
      }
      const all = Object.values(groups);
      const nest = (p, q) => p.span - q.span || (p.target < q.target ? -1 : 1);
      const near = all.filter((x) => x.group === "near").sort(nest);
      const far = all.filter((x) => x.group === "far").sort(nest);
      const sides = [all.filter((x) => x.group === "x" && x.right), all.filter((x) => x.group === "x" && !x.right)];
      for (const xs of sides) {  // the farthest in the direction of travel first
        const up = xs.reduce((t, x) => t + (x.to - x.from), 0) < 0;
        xs.sort((p, q) => (up ? p.to - q.to : q.to - p.to) || (p.target < q.target ? -1 : 1));
      }
      const count = () => sides[0].length + sides[1].length;
      const room = Math.max(1, Math.min(GUTTER_LANES, gut.lanes - near.length - far.length));
      while (count() > room) {  // merge the two neighbours whose targets are closest
        let best = null;
        for (const xs of sides) {
          for (let i = 0; i + 1 < xs.length; i++) {
            const d = Math.abs(xs[i].to - xs[i + 1].to);
            if (!best || d < best.d) best = { xs, i, d };
          }
        }
        if (!best) break;
        const [p, q] = best.xs.splice(best.i, 2);
        best.xs.splice(best.i, 0, { ...p, members: [...(p.members || [p.id]), ...(q.members || [q.id])] });
      }
      const dir = g === "head" ? -1 : 1;
      const at = (k) => gut.at + dir * k * gut.step;
      const put = (x, k) => { for (const id of x.members || [x.id]) lanes[`${g}/${id}`] = at(k); };
      near.forEach((x, k) => put(x, k));
      far.forEach((x, k) => put(x, gut.lanes - 1 - k));
      sides[0].forEach((x, k) => put(x, near.length + k));
      sides[1].forEach((x, k) => put(x, gut.lanes - 1 - far.length - k));
    }
    return lanes;
  }

  // The point at a distance along a polyline
  function pointAt(points, dist) {
    for (let i = 1; i < points.length; i++) {
      const [ax, ay] = points[i - 1], [bx, by] = points[i];
      const len = Math.hypot(bx - ax, by - ay);
      if (dist <= len || i === points.length - 1) {
        const k = len ? Math.min(1, dist / len) : 0;
        return [ax + (bx - ax) * k, ay + (by - ay) * k];
      }
      dist -= len;
    }
    return points[0];
  }

  // A loop (spec 9.5): an edge between two versions of one band whose target is not after its source, judged on
  // the positions the frame rests at (so that a glide does not switch it)
  function isLoop(inst, e, fw) {
    const A = frameBox(inst, inst.at, e.src), B = frameBox(inst, inst.at, e.dst);
    if (!A || !B) return false;
    const band = fw.bands[fw.blocks[inst.T.versions[e.src].name][0]];
    return band.flip ? B.a + B.as > A.a + A.as / 2 : B.a < A.a + A.as / 2;
  }

  // Whether an edge travels through a gutter: between two bands of one function, or a loop
  function throughGutter(inst, e) {
    const v = inst.T.versions;
    if (v[e.src].function !== v[e.dst].function) return false;
    const fw = layoutOf(inst, v[e.src].function);
    if (!fw) return false;
    return fw.blocks[v[e.src].name][0] !== fw.blocks[v[e.dst].name][0] || isLoop(inst, e, fw);
  }

  // Routes of the edges through gutters, between bands of one function and loops: leave the source on its usual
  // side into the gap after its line, run along that gap to the gutter, along the gutter (passing bands in between
  // beyond the ends of their ranks) to the gap before the target's line, and along it into the target. A loop runs
  // in the gutter before or after its band, as the frame says (`sides`, chosen at build time). No node is crossed.
  function routesInGutters(inst, at, keys, side) {
    const gaps = lineGaps(inst, at);
    const courses = {}, uses = {};
    const before = (inst.frame && inst.frame.sides) || {};
    for (const key of keys) {
      const e = inst.edges[key];
      const fn = inst.T.versions[e.src].function;
      const fw = layoutOf(inst, fn);
      const c = course(inst, at, e, side[key] || 0, fw, gaps);
      if (!c) continue;
      c.group = "x";
      const k = fw.blocks[inst.T.versions[e.src].name][0];
      if (k === fw.blocks[inst.T.versions[e.dst].name][0]) {  // a loop
        const last = fw.bands.length - 1;
        if (before[key] === "before") { c.gOut = k === 0 ? "head" : k - 1; c.group = k === 0 ? "near" : "far"; }
        else { c.gOut = k === last ? "tail" : k; c.group = "near"; }
        c.gIn = c.gOut;
        delete c.endA;
      }
      courses[key] = { c, fw, fn };
      const use = (g, from, to, right) => ((uses[fn] ||= {})[g] ||= []).push({ target: e.dst, from, to, right, group: c.group });
      if (c.gOut === c.gIn) use(c.gOut, c.exitA, c.entryA, c.right);
      else { use(c.gOut, c.exitA, c.endA, c.right); use(c.gIn, c.endA, c.entryA, c.right); }
    }
    const lanes = {};
    for (const [fn, u] of Object.entries(uses)) lanes[fn] = assignLanes(layoutOf(inst, fn), u);
    const shiftOf = (c) => c.side * 2;  // two edges between the same versions keep apart on their lane
    for (const [key, { c, fn }] of Object.entries(courses)) {
      const dst = inst.edges[key].dst;
      c.l1 = lanes[fn][`${c.gOut}/${c.group}/${dst}`] + shiftOf(c);
      c.l2 = lanes[fn][`${c.gIn}/${c.group}/${dst}`] + shiftOf(c);
    }
    // The runs in the gap after a source and before a target take slots too, so that no two edges share a
    // segment there: every edge leaving a gap has its own slot, the edges into one target share theirs (as in
    // the gutter); the run that travels farthest to its gutter lies farthest from the rank, so runs do not cross.
    const slots = {};
    const slot = (fn, g, id, dist, set) => {
      const k = `${fn}|${g.dir}|${g.at.toFixed(1)}|${id.slice(0, id.indexOf(":"))}`;
      ((slots[k] ||= { g, part: id.startsWith("in:") ? SLOT_IN : SLOT_OUT, items: {} }).items[id] ||= { dist: 0, sets: [] });
      const it = slots[k].items[id];
      it.dist = Math.max(it.dist, dist);
      it.sets.push(set);
    };
    for (const [key, { c, fn }] of Object.entries(courses)) {
      slot(fn, c.exitGap, `out:${key}`, Math.abs(c.l1 - c.x0[1]), (a) => { c.exitA = a; });
      slot(fn, c.entryGap, `in:${inst.edges[key].dst}`, Math.abs(c.l2 - c.y0[1]), (a) => { c.entryA = a; });
    }
    for (const { g, part, items } of Object.values(slots)) {
      const list = Object.entries(items).sort((p, q) => p[1].dist - q[1].dist || (p[0] < q[0] ? -1 : 1));
      if (list.length < 2) continue;  // a lone run keeps its place in the gap
      const near = part[0] * g.room, far = part[1] * g.room;
      const step = Math.min(SLOT_STEP, (far - near) / (list.length - 1));
      list.forEach(([, it], k) => { for (const set of it.sets) set(g.at + g.dir * (near + k * step)); });
    }
    const out = {};
    for (const [key, { c }] of Object.entries(courses)) {
      const l1 = c.l1, l2 = c.l2;
      let pts = [c.x0, [c.exitA, c.x0[1]], [c.exitA, l1]];
      if (c.gOut !== c.gIn) pts.push([c.endA, l1], [c.endA, l2]);
      pts.push([c.entryA, l2], [c.entryA, c.y0[1]], c.y0);
      const run = Math.abs(c.exitA - c.x0[0]), toward = Math.abs(l1 - c.x0[1]);
      const mid = pointAt(pts, run + Math.min(toward / 2, LABEL_AFTER));  // just after the source
      // a gap reached without moving along (a node at the end of its band) leaves a point twice: drop it
      pts = pts.filter((q, i) => i === 0 || Math.hypot(q[0] - pts[i - 1][0], q[1] - pts[i - 1][1]) > 0.01);
      pts = pts.map(([a, l]) => pt(inst, a, l));
      out[key] = { d: polyline(pts), mid: pt(inst, mid[0], mid[1]) };
    }
    return out;
  }

  const KIND_ORDER = ["true", "goto", "return", "call", "false"];

  // -1, 0 or 1 per drawn edge: the place of an edge among the drawn edges between the same two nodes
  function sides(inst) {
    const groups = {};
    for (const [key, e] of Object.entries(inst.edges)) {
      if (!e.g.classList.contains("lt-gone")) (groups[`${e.src}->${e.dst}`] ||= []).push(key);
    }
    const out = {};
    for (const keys of Object.values(groups)) {
      if (keys.length < 2) continue;
      keys.sort((a, b) => KIND_ORDER.indexOf(inst.edges[a].kind) - KIND_ORDER.indexOf(inst.edges[b].kind));
      keys.forEach((k, i) => { out[k] = (2 * i - (keys.length - 1)) / (keys.length - 1); });
    }
    return out;
  }

  function place(inst, at) {
    for (const [vid, p] of Object.entries(at)) if (inst.nodes[vid]) inst.nodes[vid].g.setAttribute("transform", `translate(${p[0]},${p[1]})`);
    const side = sides(inst);
    const gutter = [];  // edges between two bands of a function, and loops, are routed together (their gutter lanes)
    for (const [key, e] of Object.entries(inst.edges)) {
      if (!e.g.classList.contains("lt-gone") && throughGutter(inst, e)) gutter.push(key);
    }
    const routed = gutter.length ? routesInGutters(inst, at, gutter, side) : {};
    for (const [key, e] of Object.entries(inst.edges)) {
      if (e.g.classList.contains("lt-gone")) continue;
      const fw = inst.box.rankWrap ? banded(inst, e) : null;
      const r = key in routed ? routed[key] : fw ? routeInBand(inst, at, e, side[key] || 0, fw) : route(inst, at, e, side[key] || 0);
      if (!r) continue;
      e.path.setAttribute("d", r.d);
      e.label.setAttribute("x", r.mid[0]);
      e.label.setAttribute("y", r.mid[1]);
      // the label's box from its length in the monospace font of .lt-bbv-edge-label (12px), not measured
      const w = e.chars ? e.chars * MARK_CH + 2 * MARK_PAD : 0, h = e.chars ? MARK_H : 0;
      e.mark.setAttribute("x", r.mid[0] - w / 2);
      e.mark.setAttribute("y", r.mid[1] - h / 2);
      e.mark.setAttribute("width", w);
      e.mark.setAttribute("height", h);
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
    // an explicit height is kept; without one the drawing takes up to its default and shrinks to the room it has
    if (data.height) { canvas.style.height = `${data.height}px`; root.classList.add("lt-ga-sized"); }
    const box = data.box;
    const id = `bbv${++uid}`;
    const s = svg("svg", { viewBox: `0 0 ${box.width} ${box.height}`, class: "lt-ga-svg lt-bbv-svg", preserveAspectRatio: "xMidYMid meet" });
    s.style.maxWidth = `${box.width * 1.4}px`;
    const defs = svg("defs");
    for (const st of STATES) {
      const [len, wide] = LIT.includes(st) ? ARROW_LIT : ARROW;
      const m = svg("marker", { id: `${id}-${st}`, viewBox: "0 0 10 10", refX: "9", refY: "5", markerUnits: "userSpaceOnUse",
        markerWidth: len, markerHeight: wide, preserveAspectRatio: "none", orient: "auto-start-reverse", class: `lt-arrow st-${st}` });
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
    caption.hidden = data.captions === false; // a drawing without captions (a static CFG, `caption: none`) keeps no room for one
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(() => fitCaption(caption)).observe(caption);
    const byLabel = {};
    for (const v of Object.values(data.tables.versions)) if (!(v.label in byLabel)) byLabel[v.label] = v.block;
    if (data.zoom) {  // clickable (spec 9.5): a click on a live block asks the core to enlarge it
      s.classList.add("lt-bbv-clickable");
      gNodes.addEventListener("click", (e) => {
        const g = e.target.closest(".lt-bbv-node");
        if (!g || g.classList.contains("lt-gone") || g.classList.contains("mk-gone") || g.classList.contains("mk-absorbed")) return;
        api.zoom(g.dataset.vid);
      });
    }
    return { id, root, box, zoom: data.zoom || null, frame: null, position: 0, T: data.tables, show: data.show, colors: data.colors || {}, byLabel, callEdges: !!data.callEdges,
      store: api.frames(data.frames), gEdges, gNodes, nodes: {}, edges: {}, at: {}, raf: 0, keys: data.panel || [],
      panel: root.querySelector(".lt-ga-panel"), caption, highlight: data.highlight, kind: data.kind || null,
      edgeLabels: !!data.edgeLabels };
  }

  function show(inst, position, info) {
    cancelAnimationFrame(inst.raf);
    const f = inst.store.at(position) || {};
    inst.frame = f;
    inst.position = position;
    const pos = f.pos || {};
    const nodes = f.nodes || {};
    inst.root.classList.toggle("lt-animate", !!info.animate);
    for (const [vid, st] of Object.entries(nodes)) nodeState(inst, node(inst, vid), vid, st, position);
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
      edgeLabel(e.label, st.label || (e.kind === "true" ? "#t" : e.kind === "false" ? "#f" : ""), st.lit);
      e.chars = e.label.textContent.length;
    }
    for (const [key, e] of Object.entries(inst.edges)) if (!live.has(key)) e.g.setAttribute("class", "lt-bbv-edge lt-gone");
    const moves = glide(inst, pos, info, place);
    finish(inst, f, info, moves);
  }

  // Moves the nodes to `pos`: at once, or gliding when an animated step moves a node that was drawn. Returns
  // whether they glide.
  function glide(inst, pos, info, placer, duration = DURATION) {
    const from = inst.at;
    inst.at = pos;
    const moves = info.animate && Object.keys(pos).some((k) => from[k] && (from[k][0] !== pos[k][0] || from[k][1] !== pos[k][1]));
    if (!moves) {
      placer(inst, pos);
    } else {
      const start = Object.fromEntries(Object.keys(pos).map((n) => [n, from[n] || pos[n]]));
      const t0 = performance.now();
      const tick = (now) => {
        const k = Math.min(1, (now - t0) / duration);
        const ease = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        const at = {};
        for (const [n, p] of Object.entries(pos)) at[n] = [start[n][0] + (p[0] - start[n][0]) * ease, start[n][1] + (p[1] - start[n][1]) * ease];
        placer(inst, k < 1 ? at : pos);  // the end exactly where a fresh load draws it
        if (k < 1) inst.raf = requestAnimationFrame(tick);
      };
      placer(inst, start);
      inst.raf = requestAnimationFrame(tick);
    }
    return moves;
  }

  // The panel and caption of a frame, then the arrows at parts of the drawing (spec 8.9, 10.4), which
  // measure again, frame by frame while the nodes glide
  function finish(inst, f, info, moves, duration = DURATION) {
    renderPanel(inst, f.panel);
    inst.caption.innerHTML = richHTML(inst, f.caption || "");
    fitCaption(inst.caption);
    inst.root.dispatchEvent(new CustomEvent("lt-relayout", { bubbles: true,
      detail: moves ? { animate: true, follow: duration } : { animate: !!info.animate } }));
  }

  // ---- bbv-merge (spec 9.5, "Merge heuristics"): contexts merged two by two until the limit holds. The
  // edges of the complete graph join the borders of two nodes in a straight line, without arrowheads; their
  // width (the log of the heuristic's distance, clamped: thick for the nearest pairs) comes from the frame,
  // and a state changes their colour only, so that the width always reads as the distance.
  function distEdge(inst, key) {
    if (inst.edges[key]) return inst.edges[key];
    const g = svg("g", { class: "lt-bbv-edge lt-bbv-dist", "data-key": key });
    const path = svg("path", {});
    const label = svg("text", { class: "lt-bbv-edge-label", "text-anchor": "middle", "dominant-baseline": "middle" });
    const mark = svg("rect", { class: "lt-bbv-edge-mark", width: 0, height: 0 });
    g.append(path, label, mark);
    inst.gEdges.appendChild(g);
    const [src, dst] = key.split("--");
    return (inst.edges[key] = { g, path, label, mark, src, dst, chars: 0 });
  }

  // Where the ray from the centre of a w x h box toward (dx, dy) leaves the box, from the centre
  function border(w, h, dx, dy) {
    const t = Math.min(dx ? w / 2 / Math.abs(dx) : Infinity, dy ? h / 2 / Math.abs(dy) : Infinity);
    return [dx * t, dy * t];
  }

  function placeMerge(inst, at) {
    for (const [vid, p] of Object.entries(at)) if (inst.nodes[vid]) inst.nodes[vid].g.setAttribute("transform", `translate(${p[0]},${p[1]})`);
    for (const e of Object.values(inst.edges)) {
      if (e.g.classList.contains("lt-gone")) continue;
      const a = at[e.src], b = at[e.dst], na = inst.nodes[e.src], nb = inst.nodes[e.dst];
      if (!a || !b || !na || !nb) continue;
      const ca = [a[0] + na.w / 2, a[1] + na.h / 2], cb = [b[0] + nb.w / 2, b[1] + nb.h / 2];
      const dx = cb[0] - ca[0], dy = cb[1] - ca[1];
      let p = ca, q = cb, d = "";
      if (dx || dy) {
        const [ax, ay] = border(na.w, na.h, dx, dy), [bx, by] = border(nb.w, nb.h, -dx, -dy);
        p = [ca[0] + ax, ca[1] + ay];
        q = [cb[0] + bx, cb[1] + by];
        // boxes that overlap (a merged context drawn over the faded one it replaces) leave no segment
        if ((q[0] - p[0]) * dx + (q[1] - p[1]) * dy > 0) d = `M${p[0]},${p[1]} L${q[0]},${q[1]}`;
      }
      e.path.setAttribute("d", d);
      const mid = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
      e.label.setAttribute("x", mid[0]);
      e.label.setAttribute("y", mid[1]);
      // the label's box from its length in the monospace font of .lt-bbv-edge-label, as in `place`
      const w = e.chars ? e.chars * MARK_CH + 2 * MARK_PAD : 0, h = e.chars ? MARK_H : 0;
      e.mark.setAttribute("x", mid[0] - w / 2);
      e.mark.setAttribute("y", mid[1] - h / 2);
      e.mark.setAttribute("width", w);
      e.mark.setAttribute("height", h);
    }
  }

  function showMerge(inst, position, info) {
    cancelAnimationFrame(inst.raf);
    const f = inst.store.at(position) || {};
    inst.frame = f;
    inst.position = position;
    const nodes = f.nodes || {};
    inst.root.classList.toggle("lt-animate", !!info.animate);
    inst.root.style.setProperty("--lt-glide", `${MERGE_GLIDE}ms`);
    // an absorbed context goes under the one it meets: moved first in the drawing, then its style flushed, since
    // an element moved in the DOM starts no transition from its old style
    let moved = false;
    for (const [vid, st] of Object.entries(nodes)) {
      if (st.mark !== "absorbed") continue;
      const g = node(inst, vid).g;
      if (g !== inst.gNodes.firstChild) { inst.gNodes.insertBefore(g, inst.gNodes.firstChild); moved = true; }
    }
    if (moved) getComputedStyle(inst.gNodes.firstChild).opacity;
    for (const [vid, st] of Object.entries(nodes)) {
      const n = node(inst, vid);
      nodeState(inst, n, vid, st, position);
      // a new result fades in once the pair has met (CSS, on an animated step only); an absorbed context fades
      // out there
      if (st.arrive) n.g.classList.add("mk-arrive");
    }
    for (const [vid, n] of Object.entries(inst.nodes)) if (!(vid in nodes)) n.g.setAttribute("class", `lt-bbv-node lt-gone${n.origin}`);
    const live = new Set();
    for (const [key, st] of Object.entries(f.edges || {})) {
      const e = distEdge(inst, key);
      live.add(key);
      e.g.setAttribute("class", `lt-bbv-edge lt-bbv-dist st-${st.state || "default"}`);
      e.path.style.strokeWidth = `${st.w}px`;
      e.label.textContent = inst.edgeLabels ? st.d : "";
      e.chars = e.label.textContent.length;
    }
    for (const [key, e] of Object.entries(inst.edges)) if (!live.has(key)) e.g.setAttribute("class", "lt-bbv-edge lt-bbv-dist lt-gone");
    const moves = glide(inst, f.pos || {}, info, placeMerge, MERGE_GLIDE);
    finish(inst, f, info, moves, MERGE_GLIDE);
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

  // The enlarged copy of a block (spec 7.7, 9.5): drawn with `clickable_show` at the size computed at
  // build time, in the state of the current frame, so it shows what the step shows, in more detail.
  function zoom(inst, vid) {
    const st = inst.zoom && inst.frame && (inst.frame.nodes || {})[vid];
    const v = inst.T.versions[vid];
    if (!st || !v || st.mark === "gone" || st.mark === "absorbed") return null;
    const [w, h] = inst.zoom.sizes[vid];
    const ctx = st.lines || v.context;
    const after = st.after || v.after || [];
    const n = drawNode(inst, v, inst.zoom.show, [w, h], ctx, after, false);
    nodeState(inst, n, vid, st, inst.position);
    const p = ZOOM_PAD;
    const el = svg("svg", { viewBox: `${-p} ${-p} ${w + 2 * p} ${h + 2 * p}`, class: "lt-bbv-zoom", preserveAspectRatio: "xMidYMid meet" });
    el.appendChild(n.g);
    return { el, width: w + 2 * p, height: h + 2 * p, source: inst.nodes[vid] ? inst.nodes[vid].g : null };
  }

  function leave(inst) {
    cancelAnimationFrame(inst.raf);
    (inst.kind === "merge" ? placeMerge : place)(inst, inst.at);
  }

  Lattice.component("bbv-anim", { mount, show, leave, zoom });
  Lattice.component("bbv-cfg", { mount, show, leave, zoom });
  Lattice.component("abstract-interp-anim", { mount, show, leave, zoom });
  Lattice.component("bbv-merge", { mount, show: showMerge, leave, zoom });
})();
