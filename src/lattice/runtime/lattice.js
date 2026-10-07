// Lattice runtime: navigation state machine (spec section 7) and component host (spec section 10).
const Lattice = (() => {
  "use strict";
  const registry = {};
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  let deck = null;
  let nav = null; // { cur: {slide, step}, H: [{slide, step, kind}], tour: string|null }
  const sections = {};
  const mounted = {}; // instanceId -> { ctl, inst, el }
  const instancesBySlide = {};
  const resizeCallbacks = [];
  const dataStore = {}; // instanceId -> data fetched in directory mode
  let presenter = false;
  let passive = false; // preview (the presenter's "next" pane) and print: no input, history, storage or sync
  let printing = false;
  let previewFrame = null;
  let previewReady = false;
  let channel = null;
  let storageKey = "";
  let hudTimer = null;
  let timerStart = Date.now();
  let zoomed = null; // the enlarged element (spec 7.7): { instance, key, card, source, size }

  // ------------------------------------------------------------------ registry
  function component(name, controller) {
    registry[name] = controller;
  }

  // ------------------------------------------------------------------ frames (spec 9.3)
  function applyDelta(state, delta) {
    const out = Object.assign({}, state);
    for (const [k, v] of Object.entries(delta || {})) {
      if (v === null) delete out[k];
      else if (v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" && !Array.isArray(out[k])) out[k] = applyDelta(out[k], v);
      else out[k] = v;
    }
    return out;
  }

  function frames(store) {
    if (!store) return { count: 0, at: () => ({}) };
    if (store.format === "full") return { count: store.count, at: (i) => store.frames[Math.max(0, Math.min(i, store.count - 1))] };
    const cache = new Map();
    return {
      count: store.count,
      at(i) {
        i = Math.max(0, Math.min(i, store.count - 1));
        if (cache.has(i)) return cache.get(i);
        const k = Math.floor(i / store.interval);
        let state = store.keyframes[k];
        for (let j = k * store.interval + 1; j <= i; j++) state = applyDelta(state, store.deltas[j]);
        if (cache.size > 64) cache.clear();
        cache.set(i, state);
        return state;
      },
    };
  }

  // ------------------------------------------------------------------ helpers
  const slide = (id) => deck.slides[id];
  const steps = (id) => slide(id).steps;
  const label = (id) => (slide(id) ? slide(id).label : id);
  const detourOf = (id) => {
    const s = slide(id);
    return s && s.scope !== "root" ? deck.detours[s.scope] : null;
  };
  function topExcursion() {
    for (let i = nav.H.length - 1; i >= 0; i--) if (nav.H[i].kind === "excursion") return i;
    return -1;
  }
  function resolveTarget(id) {
    if (deck.slides[id]) return id;
    if (deck.detours[id]) return deck.detours[id].entry;
    return null;
  }

  // ------------------------------------------------------------------ state machine (spec 7.2)
  function push(kind) {
    nav.H.push({ slide: nav.cur.slide, step: nav.cur.step, kind });
  }
  function go(slideId, step, how) {
    const prev = Object.assign({}, nav.cur);
    nav.cur = { slide: slideId, step: Math.max(0, Math.min(step, steps(slideId) - 1)) };
    render(prev, how);
  }
  function tourSuccessor() {
    if (!nav.tour || !deck.tours[nav.tour]) return null;
    const list = deck.tours[nav.tour];
    const i = list.indexOf(nav.cur.slide);
    return i >= 0 && i + 1 < list.length ? list[i + 1] : null;
  }
  function nextTarget() {
    // What NEXT would do at the last step: { kind, slide } or null.
    const t = tourSuccessor();
    if (t) return { kind: "tour", slide: t };
    const n = slide(nav.cur.slide).next;
    if (n === "back") return { kind: "back", slide: returnTarget() };
    if (n && n.slide) return { kind: "next", slide: n.slide };
    return null;
  }
  function returnTarget() {
    const i = topExcursion();
    if (i >= 0) return nav.H[i].slide;
    const d = detourOf(nav.cur.slide);
    return d ? d.origin : null;
  }
  // Structural predecessor of a slide, for PREV when history is empty (spec 7.2): the tour predecessor,
  // else the previous slide on the main path, else a slide whose `next` is this one (same scope first),
  // else the slide whose branch leads here, else the origin of the detour this slide starts.
  function predecessor(id) {
    if (nav.tour && deck.tours[nav.tour]) {
      const list = deck.tours[nav.tour];
      const i = list.indexOf(id);
      if (i > 0) return list[i - 1];
    }
    const mp = deck.mainPath.indexOf(id);
    if (mp > 0) return deck.mainPath[mp - 1];
    const s = slide(id);
    const before = deck.order.filter((x) => slide(x).next && slide(x).next.slide === id);
    const same = before.find((x) => slide(x).scope === s.scope);
    if (same || before.length) return same || before[0];
    const chooser = deck.order.find((x) => slide(x).branches.some((b) => b.target === id));
    if (chooser) return chooser;
    const d = detourOf(id);
    if (d && d.entry === id) return d.origin;
    return null;
  }
  // A step whose arrival through NEXT enters a detour (spec 6.4): { id, blocking }, or null.
  const stepDetour = (id, step) => (slide(id).stepDetours || {})[step] || null;

  // Checkpoints (spec 6.5): the steps where two quick presses of a skip key stop, computed at build time.
  // A slide without the field has its last step as its only checkpoint.
  const checkpointsOf = (id) => slide(id).checkpoints || [steps(id) - 1];
  function nextCheckpoint(id, step) {
    const k = checkpointsOf(id).find((c) => c > step);
    return k === undefined ? step : k;
  }
  function prevCheckpoint(id, step) {
    const before = checkpointsOf(id).filter((c) => c < step);
    return before.length ? before[before.length - 1] : 0;
  }

  // Multi-step moves within a slide play the intermediate steps in rapid succession, so that
  // animations are seen rather than skipped (spec 7.2, SKIP). A new move cancels a running one.
  // Detour steps on the way are not entered; a blocking one stops the playback in front of it.
  // `hold` ({ step, until }) keeps the playback from passing `step` before the time `until`: the first
  // of two quick presses waits there for the second (spec 7.6). `checkpoint` marks a playback to a
  // checkpoint, from which a following double press counts.
  let playTimer = null;
  let playing = null; // the playback under way: { slide, target, dir, checkpoint }
  function playSteps(target, opts = {}) {
    stopPlaying();
    const total = Math.abs(target - nav.cur.step);
    if (!total) return;
    const interval = Math.max(30, Math.min(90, 1000 / total));
    const hold = opts.hold || null;
    playing = { slide: nav.cur.slide, target, dir: Math.sign(target - nav.cur.step), checkpoint: !!opts.checkpoint };
    const tick = () => {
      const cur = nav.cur.step;
      if (cur === target) { playing = null; return; }
      const dir = Math.sign(target - cur);
      if (hold && cur === hold.step && performance.now() < hold.until) {
        playTimer = setTimeout(tick, hold.until - performance.now());
        return;
      }
      const d = dir > 0 ? stepDetour(nav.cur.slide, cur + 1) : null;
      if (d && d.blocking) { playing = null; return flash("Cannot step detour"); }
      go(nav.cur.slide, cur + dir, { kind: "step", dir });
      if (nav.cur.step !== target) playTimer = setTimeout(tick, interval);
      else playing = null;
    };
    tick();
  }
  function stopPlaying() {
    clearTimeout(playTimer);
    playTimer = null;
    playing = null;
  }

  const actions = {
    next() {
      const cur = nav.cur;
      if (cur.step < steps(cur.slide) - 1) {
        const k = cur.step + 1;
        go(cur.slide, k, { kind: "step", dir: 1 });
        const d = stepDetour(cur.slide, k); // a detour step: arriving on it enters the detour (spec 6.4)
        if (d) actions.enter(d.id);
        return;
      }
      const t = tourSuccessor();
      if (t) { push("forward"); return go(t, 0, { kind: "next", dir: 1 }); }
      const n = slide(cur.slide).next;
      if (n === "back") return actions.return();
      if (n && n.slide) { push("forward"); return go(n.slide, 0, { kind: "next", dir: 1 }); }
      flash("End of path");
    },
    prev() {
      const cur = nav.cur;
      if (cur.step > 0) {
        let k = cur.step - 1;
        while (k > 0 && stepDetour(cur.slide, k)) k--; // detour steps show nothing new going backward
        return go(cur.slide, k, { kind: "step", dir: -1 });
      }
      if (nav.H.length) {
        const e = nav.H.pop();
        return go(e.slide, e.step, { kind: e.kind === "excursion" ? "return" : "prev", dir: -1 });
      }
      const p = predecessor(cur.slide); // no history: walk the structure backward, without recording it
      if (p) return go(p, steps(p) - 1, { kind: "prev", dir: -1 });
      flash("No previous slide");
    },
    "skip-forward"() { playSteps(Math.min(nav.cur.step + 10, steps(nav.cur.slide) - 1)); },
    "skip-back"() { playSteps(Math.max(nav.cur.step - 10, 0)); },
    "last-step"() { playSteps(steps(nav.cur.slide) - 1); },
    "first-step"() { playSteps(0); },
    "skip-detour"() {
      // Step over the detour step(s) that follow, without entering them (spec 7.2, SKIP-DETOUR).
      const cur = nav.cur;
      let k = cur.step;
      while (k + 1 < steps(cur.slide) && stepDetour(cur.slide, k + 1)) k++;
      if (k === cur.step) return flash("No detour step next");
      go(cur.slide, Math.min(k + 1, steps(cur.slide) - 1), { kind: "step", dir: 1 });
    },
    choose(key) {
      const s = slide(nav.cur.slide);
      const b = s.branches.find((o) => o.key === key);
      if (b) { push("forward"); return go(b.target, 0, { kind: "branch", dir: 1 }); }
      const dId = s.detours.find((id) => deck.detours[id].key === key);
      if (dId) return actions.enter(dId);
      return false;
    },
    down() {
      const s = slide(nav.cur.slide);
      if (s.detours.length) return actions.enter(s.detours[0]);
      flash("No detour here");
    },
    enter(detourId) {
      const d = deck.detours[detourId];
      if (!d || !d.entry) return;
      push("excursion");
      go(d.entry, 0, { kind: "detour", dir: 1 });
    },
    jump(target) {
      const t = resolveTarget(target);
      if (!t || t === nav.cur.slide) return;
      push("excursion");
      go(t, 0, { kind: "link", dir: 1 });
    },
    return() {
      const i = topExcursion();
      if (i >= 0) {
        const e = nav.H[i];
        nav.H = nav.H.slice(0, i);
        return go(e.slide, e.step, { kind: "return", dir: -1 });
      }
      const d = detourOf(nav.cur.slide);
      if (d) return go(d.origin, steps(d.origin) - 1, { kind: "return", dir: -1 });
      flash("Nothing to return to");
    },
    home() {
      nav.H = [];
      go(deck.start, 0, { kind: "link", dir: -1 });
    },
    tour() {
      const names = Object.keys(deck.tours);
      if (!names.length) return flash("No tours defined");
      const i = nav.tour ? names.indexOf(nav.tour) : -1;
      nav.tour = i + 1 < names.length ? names[i + 1] : null;
      flash(nav.tour ? `Tour: ${nav.tour}` : "Tour off");
      save();
      broadcast();
    },
    overview() { openOverview(); },
    goto() { openGoto(); },
    presenter() {
      if (presenter) return;
      const url = location.pathname + location.search + (location.search ? "&" : "?") + "presenter" + location.hash;
      window.open(url, "lattice-presenter");
    },
    "enter-detour"() { actions.down(); },
  };

  // ------------------------------------------------------------------ rendering
  function transitionFor(how, target) {
    if (!how || how.kind === "step" || how.kind === "sync" || how.kind === "scrub" || how.kind === "hash") return null;
    const back = (name) => (name === "zoom" ? "zoom-out" : name === "slide" ? "slide-back" : name);
    if (how.kind === "return") return "zoom-out";
    if (how.kind === "prev") return back(deck.transitions.next);
    const name = slide(target).transition || deck.transitions[how.kind] || deck.transitions.next;
    if (how.dir < 0) return back(name);
    return name === "zoom" ? "zoom-in" : name;
  }

  // Panel of variables shared by animation components: scalars, lists and maps.
  function renderPanel(el, panel, keys) {
    if (!el) return;
    const entries = Object.entries(panel || {}).filter(([k]) => !keys || keys.includes(k));
    if (keys) entries.sort((a, b) => keys.indexOf(a[0]) - keys.indexOf(b[0]));
    el.hidden = entries.length === 0;
    el.innerHTML = entries.map(([k, v]) => {
      let body;
      if (Array.isArray(v)) body = `<div class="lt-pv-list">${v.map((x) => `<span>${esc(x)}</span>`).join("") || '<span class="lt-muted">empty</span>'}</div>`;
      else if (v && typeof v === "object") body = `<table class="lt-pv-map"><tr>${Object.keys(v).map((x) => `<th>${esc(x)}</th>`).join("")}</tr><tr>${Object.values(v).map((x) => `<td>${esc(x)}</td>`).join("")}</tr></table>`;
      else body = `<div class="lt-pv-scalar">${esc(v)}</div>`;
      return `<div class="lt-pv"><div class="lt-pv-name">${esc(k)}</div>${body}</div>`;
    }).join("");
  }

  function mountSlide(id) {
    for (const instId of instancesBySlide[id] || []) {
      if (mounted[instId]) continue;
      const meta = deck.instances[instId];
      const ctl = registry[meta.component];
      if (!ctl || !(meta.data || meta.url)) continue; // static instances need no runtime
      const el = sections[id].querySelector(`[data-instance="${CSS.escape(instId)}"]`);
      if (!el) continue;
      let data = dataStore[instId];
      if (data === undefined) {
        const dataEl = meta.data ? document.getElementById(meta.data) : null;
        data = dataEl ? JSON.parse(dataEl.textContent) : null;
      }
      const api = {
        instanceId: instId,
        frames,
        goto: (t) => actions.jump(t),
        presenter,
        onResize: (cb) => resizeCallbacks.push(cb),
        palette: getComputedStyle(document.documentElement),
        zoom: (key) => openZoom(instId, String(key)),
      };
      try {
        mounted[instId] = { ctl, inst: ctl.mount(el, data, api), el };
      } catch (err) {
        console.error(`lattice: mount failed for ${instId}`, err);
      }
    }
  }

  // ------------------------------------------------------------------ column widths (spec 3.8, 10.4)
  // A `columns` container marked by the build ([data-lt-cols]) gives each of its columns the flex value of
  // the current position of the columns track, or the column's own (`data-lt-flex`). An animated change
  // measures the columns before and after it, moves their boxes in slide pixels while their contents keep a
  // fixed width (their final one; a collapsing column keeps its own and fades out), then sets the final
  // values. The measures are for display only: every width comes from the build.
  const SHUT = "0 0 0px";
  const QUICK_COLUMNS_MS = 140; // a change that interrupts another (skip playback)
  const columnMoves = new Map(); // container -> pending end of its move
  const columnsAt = new WeakMap(); // container -> the targets last placed
  const columnsOf = (box) => Array.from(box.children).filter((c) => c.classList.contains("lt-column"));
  const columnInner = (col) => Array.from(col.children).find((c) => c.classList.contains("lt-column-in"));

  // A column at rest: its final flex value, no transition. A move's transitions may still be running when its timer
  // ends (they start at the next frame, which comes late on a busy page), and clearing `transition` does not stop
  // them in Chromium: they are cancelled, or the box would keep moving after the arrows measured it.
  function restColumn(col, flex) {
    const shut = flex === SHUT;
    const inner = columnInner(col);
    for (const el of [col, inner]) if (el && el.getAnimations) el.getAnimations().forEach((a) => a.cancel());
    col.style.transition = "";
    col.style.marginLeft = "";
    col.style.marginRight = "";
    col.style.flex = flex || "";
    col.classList.remove("lt-col-moving", "lt-col-closing");
    col.classList.toggle("lt-col-shut", shut);
    col.inert = shut;
    col.ltShut = shut;
    if (inner) {
      inner.style.transition = "";
      inner.style.opacity = "";
      if (!shut) inner.style.width = ""; // a collapsed column keeps the width of its content, to come back as it was
    }
  }

  function placeColumns(box, state, animate) {
    const cols = columnsOf(box);
    const targets = cols.map((c) => (c.dataset.ltCol && c.dataset.ltCol in state ? state[c.dataset.ltCol] : c.dataset.ltFlex || ""));
    const key = targets.join("|");
    const moving = columnMoves.get(box);
    if (moving) clearTimeout(moving);
    columnMoves.delete(box);
    if (!moving && columnsAt.get(box) === key) return;
    columnsAt.set(box, key);
    const ms = Number(box.dataset.ltDuration || 0);
    if (!animate || !ms || reducedMotion() || !box.getClientRects().length) {
      cols.forEach((c, i) => restColumn(c, targets[i]));
      relayoutColumns(box, 0);
      return;
    }
    const duration = moving ? Math.min(ms, QUICK_COLUMNS_MS) : ms;
    const width = (c) => parseFloat(getComputedStyle(c).width) || 0;
    const margins = (c) => { const cs = getComputedStyle(c); return [parseFloat(cs.marginLeft) || 0, parseFloat(cs.marginRight) || 0]; };
    // where the columns are now (halfway through a move, too)
    const w0 = cols.map(width), m0 = cols.map(margins);
    const was = cols.map((c) => (c.ltShut !== undefined ? c.ltShut : c.classList.contains("lt-col-shut")));
    const inners = cols.map(columnInner);
    const content0 = inners.map((n, i) => (n && n.style.width ? parseFloat(n.style.width) : w0[i]));
    const opacity0 = inners.map((n) => (n ? getComputedStyle(n).opacity : "1"));
    // where they will be (a move under way is dropped first, or its transitions would still be measured)
    for (const el of [...cols, ...inners]) if (el && el.getAnimations) el.getAnimations().forEach((a) => a.cancel());
    cols.forEach((c, i) => restColumn(c, targets[i]));
    const w1 = cols.map(width), m1 = cols.map(margins);
    // back to the start, then move
    cols.forEach((c, i) => {
      const shut = targets[i] === SHUT;
      c.classList.remove("lt-col-shut");
      c.classList.add("lt-col-moving");
      c.classList.toggle("lt-col-closing", shut && !was[i]);
      c.style.flex = `0 1 ${w0[i]}px`;
      c.style.marginLeft = `${m0[i][0]}px`;
      c.style.marginRight = `${m0[i][1]}px`;
      const n = inners[i];
      if (n) {
        n.style.width = `${shut ? content0[i] : w1[i]}px`;
        n.style.opacity = opacity0[i];
      }
    });
    void box.offsetWidth;
    const ease = `${duration}ms ease-in-out`;
    cols.forEach((c, i) => {
      const shut = targets[i] === SHUT;
      c.style.transition = `flex-basis ${ease}, margin-left ${ease}, margin-right ${ease}`;
      c.style.flex = `0 1 ${w1[i]}px`;
      c.style.marginLeft = `${m1[i][0]}px`;
      c.style.marginRight = `${m1[i][1]}px`;
      const n = inners[i];
      if (n) {
        n.style.transition = `opacity ${ease}`;
        n.style.opacity = shut ? "0" : "1";
      }
    });
    columnMoves.set(box, setTimeout(() => {
      columnMoves.delete(box);
      cols.forEach((c, i) => restColumn(c, targets[i]));
      relayoutColumns(box, 0);
    }, duration + 30));
    relayoutColumns(box, duration);
  }

  // Runtimes that measure the slide (arrows) follow the columns: frame by frame while they move (`follow`).
  function relayoutColumns(box, follow) {
    box.dispatchEvent(new CustomEvent("lt-relayout", { bubbles: true, detail: follow ? { animate: true, follow } : { animate: false } }));
  }

  function applyStep(id, step, info) {
    const s = slide(id);
    const row = s.positions[step] || [];
    const posOf = {};
    s.tracks.forEach((t, i) => { posOf[t.instance || t.id] = row[i] || 0; });
    const boxes = $$("[data-lt-cols]", sections[id]);
    if (boxes.length) {
      const ci = s.tracks.findIndex((t) => t.kind === "columns");
      const state = ci >= 0 && s.columns ? s.columns[row[ci] || 0] || {} : {};
      for (const box of boxes) placeColumns(box, state, info.animate);
    }
    if ("reveal" in posOf) {
      const shown = posOf.reveal;
      for (const el of $$("[data-lt-reveal]", sections[id])) {
        el.classList.toggle("lt-hidden", Number(el.dataset.ltReveal) > shown);
      }
    }
    // badge=step|next (spec 3.9): shown from, or only at, the step before the detour's detour step
    for (const el of $$("[data-lt-badge]", sections[id])) {
      const at = Object.entries(s.stepDetours || {})
        .filter(([, d]) => d.id === el.dataset.ltDetour).map(([k]) => Number(k));
      const shown = el.dataset.ltBadge === "next" ? at.includes(step + 1) : at.some((k) => step >= k - 1);
      el.classList.toggle("lt-hidden", !shown);
    }
    const prevRow = info.fromStep != null ? s.positions[info.fromStep] || [] : null;
    for (const instId of instancesBySlide[id] || []) {
      const m = mounted[instId];
      if (!m) continue;
      const tIndex = s.tracks.findIndex((t) => t.instance === instId);
      const pos = tIndex >= 0 ? row[tIndex] : 0;
      const from = prevRow && tIndex >= 0 ? prevRow[tIndex] : null;
      if (info.sameSlide && from === pos && !info.force) continue;
      try {
        m.ctl.show(m.inst, pos, { from, direction: from == null ? 0 : Math.sign(pos - from), animate: info.animate });
      } catch (err) {
        console.error(`lattice: show failed for ${instId}`, err);
      }
    }
  }

  function render(prev, how) {
    closeZoom({ instant: true, quiet: true }); // a position change, from anywhere, closes an enlarged element
    const id = nav.cur.slide;
    const sameSlide = prev && prev.slide === id;
    if (!sameSlide) {
      if (prev && prev.slide && sections[prev.slide]) {
        sections[prev.slide].hidden = true;
        sections[prev.slide].classList.remove("lt-current");
        for (const instId of instancesBySlide[prev.slide] || []) {
          const m = mounted[instId];
          if (m && m.ctl.leave) try { m.ctl.leave(m.inst); } catch (e) { console.error(e); }
        }
      }
      const sec = sections[id];
      sec.hidden = false;
      sec.classList.add("lt-current");
      mountSlide(id);
      for (const instId of instancesBySlide[id] || []) {
        const m = mounted[instId];
        if (m && m.ctl.enter) try { m.ctl.enter(m.inst); } catch (e) { console.error(e); }
      }
      const tr = transitionFor(how, id);
      sec.classList.remove(...Array.from(sec.classList).filter((c) => c.startsWith("lt-anim-")));
      if (tr && tr !== "none") {
        void sec.offsetWidth;
        sec.classList.add(`lt-anim-${tr}`);
      }
    }
    // scrubbing, a change of the URL hash, previews and printing never animate (spec 10.1)
    const still = how && (how.kind === "scrub" || how.kind === "hash");
    const adjacent = sameSlide && Math.abs(prev.step - nav.cur.step) === 1 && !passive && !still;
    applyStep(id, nav.cur.step, { sameSlide, fromStep: sameSlide ? prev.step : null, animate: adjacent, force: !sameSlide });
    updateHud();
    if (passive) return;
    updateHash();
    save();
    if (!how || how.kind !== "sync") broadcast();
    if (presenter) updatePresenter();
  }

  // ------------------------------------------------------------------ HUD
  function updateHud() {
    const crumbs = $("#lt-crumbs");
    const parts = nav.H.filter((e) => e.kind === "excursion").map((e) => esc(label(e.slide)));
    const d = detourOf(nav.cur.slide);
    if (!parts.length && d) parts.push(esc(label(d.origin)));
    parts.push(`<b>${esc(label(nav.cur.slide))}</b>`);
    crumbs.innerHTML = parts.join('<span class="lt-sep">\u21b3</span>');

    const s = slide(nav.cur.slide);
    const bits = [];
    if (s.steps > 14) bits.push(`<span class="lt-where">step ${nav.cur.step + 1}/${s.steps}</span>`);
    else if (s.steps > 1) {
      const dot = (i) => `<i class="${[i <= nav.cur.step ? "on" : "", stepDetour(nav.cur.slide, i) ? "dt" : ""].join(" ").trim()}"></i>`;
      bits.push(`<span class="lt-steps">${Array.from({ length: s.steps }, (_, i) => dot(i)).join("")}</span>`);
    }
    // the Down hint names the first detour, unless all its badges are waiting for their step (spec 3.9)
    const firstBadges = s.detours.length ? $$(`.lt-detour-badge[data-lt-detour="${CSS.escape(s.detours[0])}"]`, sections[nav.cur.slide]) : [];
    const waiting = firstBadges.length > 0 && firstBadges.every((b) => b.dataset.ltBadge && b.classList.contains("lt-hidden"));
    if (s.detours.length && !waiting) {
      bits.push(`<span class="lt-hint"><kbd>\u2193</kbd>${esc(deck.detours[s.detours[0]].label)}</span>`);
    }
    if (topExcursion() >= 0 || d) bits.push(`<span class="lt-hint"><kbd>\u2191</kbd>${esc(label(returnTarget()))}</span>`);
    const mp = deck.mainPath.indexOf(nav.cur.slide);
    if (nav.tour) bits.push(`<span class="lt-where">tour ${esc(nav.tour)}</span>`);
    if (mp >= 0) bits.push(`<span class="lt-where">${mp + 1}/${deck.mainPath.length}</span>`);
    else if (d) bits.push(`<span class="lt-where">${d.slides.indexOf(nav.cur.slide) + 1}/${d.slides.length}</span>`);
    else if (s.offpath) bits.push(`<span class="lt-where">off path</span>`);
    $("#lt-progress").innerHTML = bits.join("");
  }

  function flash(message) {
    let el = $("#lt-flash");
    if (!el) {
      el = document.createElement("div");
      el.id = "lt-flash";
      $("#lt-viewport").appendChild(el);
    }
    el.textContent = message;
    el.classList.add("on");
    clearTimeout(hudTimer);
    hudTimer = setTimeout(() => el.classList.remove("on"), 1200);
    return false;
  }

  // ------------------------------------------------------------------ persistence (spec 7.4)
  function updateHash() {
    const h = `#/${encodeURIComponent(nav.cur.slide)}/${nav.cur.step}`;
    if (location.hash !== h) history.replaceState(null, "", h);
  }
  function save() {
    try { sessionStorage.setItem(storageKey, JSON.stringify(nav)); } catch (e) { /* storage unavailable */ }
  }
  function parseHash() {
    const m = /^#\/([^/]+)(?:\/(\d+))?$/.exec(location.hash);
    if (!m) return null;
    const id = resolveTarget(decodeURIComponent(m[1]));
    return id ? { slide: id, step: Math.min(Number(m[2] || 0), steps(id) - 1) } : null;
  }
  function restore() {
    const fromHash = parseHash();
    let saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(storageKey) || "null"); } catch (e) { saved = null; }
    const valid = (e) => e && deck.slides[e.slide];
    if (saved && valid(saved.cur) && (!fromHash || (fromHash.slide === saved.cur.slide && fromHash.step === saved.cur.step))) {
      saved.H = (saved.H || []).filter(valid);
      if (saved.tour && !deck.tours[saved.tour]) saved.tour = null;
      return saved;
    }
    return { cur: fromHash || { slide: deck.start, step: 0 }, H: [], tour: null };
  }

  // ------------------------------------------------------------------ sync (spec 7.5)
  function broadcast() {
    if (channel) channel.postMessage({ nav: JSON.parse(JSON.stringify(nav)) });
  }
  function onRemote(msg) {
    if (msg && "zoom" in msg) {
      if (msg.zoom) openZoom(msg.zoom.instance, msg.zoom.key, { remote: true });
      else closeZoom({ remote: true });
      return;
    }
    if (!msg || !msg.nav || !deck.slides[msg.nav.cur.slide]) return;
    const prev = Object.assign({}, nav.cur);
    nav = msg.nav;
    render(prev, { kind: "sync", dir: 0 });
  }


  // ------------------------------------------------------------------ enlarged elements (spec 7.7)
  // A component's controller may define zoom(inst, key) -> { el, width, height, source } | null; the
  // core shows `el` in a card over the slide pane, blurs the slide, and grows the card out of `source`.
  // The layer is not a position: it is never saved, hashed or recorded, and any render closes it.
  const ZOOM_FILL = 0.8;     // the card fits in 80% of the slide's width and height
  const ZOOM_MAX = 4.5;      // ... magnifying the element's own units at most this much
  const ZOOM_MS = 350;
  const MODIFIERS = new Set(["Shift", "Control", "Alt", "Meta", "AltGraph", "CapsLock", "OS", "Hyper", "Super"]);
  let swallowClick = false;
  const reducedMotion = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function zoomLayer() {
    let layer = $("#lt-zoom");
    if (!layer) {
      layer = document.createElement("div");
      layer.id = "lt-zoom";
      $("#lt-stage").appendChild(layer);
    }
    return layer;
  }

  // The card's box in pixels relative to the stage: the element's size magnified to fill 80% of the
  // slide (capped), centred on the slide as it is shown.
  function zoomBox(size) {
    const stage = $("#lt-stage").getBoundingClientRect();
    const vp = $("#lt-viewport").getBoundingClientRect();
    const W = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--lt-w"));
    const H = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--lt-h"));
    const scale = vp.width / W;
    const m = Math.min(ZOOM_FILL * W / size.width, ZOOM_FILL * H / size.height, ZOOM_MAX);
    const w = size.width * m * scale, h = size.height * m * scale;
    return { left: vp.left - stage.left + (vp.width - w) / 2, top: vp.top - stage.top + (vp.height - h) / 2, width: w, height: h };
  }

  function placeCard(card, box) {
    Object.assign(card.style, { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` });
  }

  // The transform that puts the card over its source element: same left edge and width, same top
  // (extra rows of the card unfold below as it grows).
  function sourceTransform(source, box) {
    if (!source || !source.isConnected) return null;
    const r = source.getBoundingClientRect();
    if (!r.width || !r.height || getComputedStyle(source).opacity === "0") return null;
    const stage = $("#lt-stage").getBoundingClientRect();
    const k = r.width / box.width;
    return `translate(${r.left - stage.left - box.left}px, ${r.top - stage.top - box.top}px) scale(${k})`;
  }

  function openZoom(instId, key, opts = {}) {
    if (passive || !nav) return;
    const m = mounted[instId];
    if (!m || !m.ctl.zoom || deck.instances[instId].slide !== nav.cur.slide) return;
    let r = null;
    try { r = m.ctl.zoom(m.inst, key); } catch (err) { console.error(`lattice: zoom failed for ${instId}`, err); }
    if (!r || !r.el) return;
    stopPlaying();
    closeZoom({ instant: true, quiet: true });
    const layer = zoomLayer();
    const card = document.createElement("div");
    card.className = "lt-zoom-card";
    card.appendChild(r.el);
    layer.appendChild(card);
    const size = { width: r.width, height: r.height };
    const box = zoomBox(size);
    placeCard(card, box);
    zoomed = { instance: instId, key, card, source: r.source, size };
    layer.classList.add("lt-on");
    $("#lt-stage").classList.add("lt-zoomed");
    const from = reducedMotion() ? null : sourceTransform(r.source, box);
    if (from && card.animate) card.animate([{ transform: from }, { transform: "none" }], { duration: ZOOM_MS, easing: "cubic-bezier(.2,.8,.25,1)" });
    if (!opts.remote) broadcastZoom({ instance: instId, key });
  }

  function closeZoom(opts = {}) {
    if (!zoomed) return;
    const z = zoomed;
    zoomed = null; // input is back to normal at once, while the card shrinks
    const layer = zoomLayer();
    layer.classList.remove("lt-on");
    $("#lt-stage").classList.remove("lt-zoomed");
    const to = opts.instant || reducedMotion() ? null : sourceTransform(z.source, zoomBox(z.size));
    if (to && z.card.animate) {
      z.card.classList.add("lt-closing");
      const a = z.card.animate([{ transform: "none" }, { transform: to, opacity: 0.6 }], { duration: ZOOM_MS * 0.8, easing: "cubic-bezier(.4,0,.6,1)", fill: "forwards" });
      a.onfinish = () => z.card.remove();
    } else {
      z.card.remove();
    }
    if (!opts.remote && !opts.quiet) broadcastZoom(null);
  }

  function broadcastZoom(zoom) {
    if (channel) channel.postMessage({ zoom });
  }

  // While an element is enlarged, a press anywhere outside its card closes it and does nothing else:
  // no link, badge or branch option, no timer reset, no scrubber move (capture phase, before them).
  function onZoomPointer(e) {
    if (e.type === "pointerdown") {
      swallowClick = false;
      if (!zoomed || zoomed.card.contains(e.target)) return;
      swallowClick = true; // the mousedown and click of this press are swallowed too
      e.preventDefault();
      e.stopPropagation();
      closeZoom();
    } else if (swallowClick) {
      e.preventDefault();
      e.stopPropagation();
    }
  }
  function onZoomClick(e) {
    if (!swallowClick) return;
    swallowClick = false;
    e.preventDefault();
    e.stopPropagation();
  }

  // ------------------------------------------------------------------ overlays
  function closeOverlay() {
    const o = $("#lt-overlay");
    o.hidden = true;
    o.innerHTML = "";
  }
  const overlayOpen = () => !$("#lt-overlay").hidden;

  function slideButton(id, extra = "") {
    const cur = id === nav.cur.slide ? " current" : "";
    return `<button type="button" class="lt-ov-item${cur}" data-jump="${esc(id)}">${esc(label(id))}${extra}</button>`;
  }

  function openOverview() {
    const listed = new Set();
    const tree = (id, depth) => {
      listed.add(id);
      let out = `<li>${slideButton(id)}`;
      const s = slide(id);
      for (const dId of s.detours) {
        const d = deck.detours[dId];
        out += `<ul class="lt-ov-detour"><li class="lt-ov-label">${d.key ? `<kbd>${esc(d.key)}</kbd>` : "\u2193"} ${esc(d.label)}</li>`;
        for (const x of d.slides) out += tree(x, depth + 1);
        out += "</ul>";
      }
      if (s.branches.length) {
        out += `<ul class="lt-ov-branch">`;
        for (const b of s.branches) out += `<li class="lt-ov-label"><kbd>${esc(b.key)}</kbd> ${esc(b.label || label(b.target))}</li>`;
        out += "</ul>";
      }
      return out + "</li>";
    };
    let html = `<div class="lt-panel lt-overview"><h2>Overview</h2>${overviewMap()}<ol class="lt-ov-main">`;
    for (const id of deck.order) {
      const s = slide(id);
      if (s.scope !== "root" || s.offpath || listed.has(id)) continue;
      html += tree(id, 0);
    }
    html += "</ol>";
    const rest = deck.order.filter((id) => !listed.has(id));
    if (rest.length) html += `<h3>Off path</h3><ul class="lt-ov-rest">${rest.map((id) => `<li>${slideButton(id)}</li>`).join("")}</ul>`;
    html += "</div>";
    const o = $("#lt-overlay");
    o.innerHTML = html;
    o.hidden = false;
    const cur = $(".lt-ov-item.current", o);
    if (cur) cur.focus({ preventScroll: true });
    const node = $(".lt-ovn.current", o);
    if (node) node.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function overviewMap() {
    const ov = deck.overview;
    if (!ov || !ov.nodes || !Object.keys(ov.nodes).length) return "";
    const visited = new Set(nav.H.map((e) => e.slide));
    const edges = ov.edges.map((e) => `<path class="k-${e.kind}" d="${e.path}"${e.kind === "link" ? "" : ' marker-end="url(#lt-ov-arrow)"'}/>`).join("");
    const nodes = Object.entries(ov.nodes).map(([id, n]) => {
      const s = slide(id);
      const cls = ["lt-ovn", id === nav.cur.slide ? "current" : "", visited.has(id) ? "visited" : "",
        s.offpath ? "offpath" : "", s.scope !== "root" ? "detour" : ""].join(" ");
      return `<g class="${cls}" data-jump="${esc(id)}" transform="translate(${n.x - n.w / 2},${n.y - n.h / 2})">` +
        `<rect width="${n.w}" height="${n.h}" rx="7"/><text x="${n.w / 2}" y="${n.h / 2}">${esc(n.label)}</text></g>`;
    }).join("");
    return `<div class="lt-ov-map"><svg viewBox="0 0 ${ov.width} ${ov.height}" width="${ov.width * 1.15}" height="${ov.height * 1.15}">` +
      `<defs><marker id="lt-ov-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z"/></marker></defs>` +
      `<g class="lt-ov-edges">${edges}</g>${nodes}</svg></div>`;
  }

  function fuzzy(q, text) {
    q = q.toLowerCase();
    text = text.toLowerCase();
    if (text.includes(q)) return 2;
    let i = 0;
    for (const c of text) if (c === q[i]) i++;
    return i === q.length ? 1 : 0;
  }

  function openGoto() {
    const o = $("#lt-overlay");
    o.innerHTML = `<div class="lt-panel lt-goto"><input type="text" placeholder="Go to slide" aria-label="Go to slide"><ul></ul></div>`;
    o.hidden = false;
    const input = $("input", o);
    const list = $("ul", o);
    let sel = 0;
    let matches = [];
    const refresh = () => {
      const q = input.value.trim();
      matches = deck.order
        .map((id) => ({ id, score: q ? Math.max(fuzzy(q, label(id)), fuzzy(q, id)) : 1 }))
        .filter((m) => m.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 12);
      sel = Math.min(sel, Math.max(0, matches.length - 1));
      list.innerHTML = matches
        .map((m, i) => `<li class="${i === sel ? "sel" : ""}"><button type="button" data-jump="${esc(m.id)}">${esc(label(m.id))}<small>${esc(m.id)}</small></button></li>`)
        .join("");
    };
    input.addEventListener("input", () => { sel = 0; refresh(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { sel = Math.min(sel + 1, matches.length - 1); refresh(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); refresh(); e.preventDefault(); }
      else if (e.key === "Enter" && matches[sel]) { const t = matches[sel].id; closeOverlay(); actions.jump(t); }
      else if (e.key === "Escape") closeOverlay();
      e.stopPropagation();
    });
    refresh();
    input.focus();
  }

  // ------------------------------------------------------------------ presenter view (spec 7.5)
  function buildPresenter() {
    const panel = $("#lt-presenter-panel");
    const W = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--lt-w"));
    const H = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--lt-h"));
    panel.innerHTML = `
      <div class="lt-pp-top"><span class="lt-pp-timer" title="Click to reset">00:00</span><span class="lt-pp-where"></span></div>
      <div class="lt-pp-scrub" hidden><input type="range" min="0" max="1" step="1" value="0" aria-label="Step of the current slide"><span class="lt-pp-scrub-label"></span></div>
      <h3>Next <span class="lt-pp-next-label"></span></h3>
      <div class="lt-pp-next"><iframe class="lt-pp-preview" title="Next" tabindex="-1" style="aspect-ratio:${W} / ${H}"></iframe><div class="lt-pp-next-none" hidden></div></div>
      <h3>Moves</h3><ul class="lt-pp-moves"></ul>
      <h4 class="lt-pp-keys-title">Keybindings</h4><ul class="lt-pp-keys">${keybindingsList()}</ul>
      <h3>Notes</h3><div class="lt-pp-notes"></div>`;
    const range = $(".lt-pp-scrub input", panel);
    range.addEventListener("input", () => {
      const i = Number(range.value);
      if (i !== nav.cur.step) go(nav.cur.slide, i, { kind: "scrub", dir: 0 });
    });
    range.addEventListener("change", () => range.blur()); // arrow keys go back to the deck
    previewFrame = $(".lt-pp-preview", panel);
    window.addEventListener("message", (e) => {
      if (e.source === previewFrame.contentWindow && e.data && e.data.lattice === "preview-ready") {
        previewReady = true;
        updatePreview();
      }
    });
    previewFrame.src = location.pathname + "?preview";
  }

  // The Keybindings section of the presenter panel: every global action with its keys (spec 7.5).
  const ACTION_LABELS = {
    next: "next step or slide", prev: "previous step, or undo the last move",
    "skip-forward": "10 steps forward", "skip-back": "10 steps back", "last-step": "last step of the slide",
    "first-step": "first step of the slide",
    "skip-detour": "step over the next detour step",
    "enter-detour": "enter the first detour", return: "return from a detour or jump",
    overview: "overview", goto: "go to a slide", presenter: "presenter view", tour: "cycle through tours",
    home: "start of the deck, clearing history",
  };
  const KEY_NAMES = { " ": "Space", ArrowRight: "→", ArrowLeft: "←", ArrowUp: "↑", ArrowDown: "↓" };
  const keyName = (k) => k.split("+").map((part) => KEY_NAMES[part] || part).join("+");
  function keybindingsList() {
    const rows = Object.entries(deck.keys).map(([action, keys]) =>
      `<li><span class="lt-pp-kbd">${keys.map((k) => `<kbd>${esc(keyName(k))}</kbd>`).join("")}</span>` +
      `<span>${esc(ACTION_LABELS[action] || action)}</span></li>`);
    const fwd = (deck.keys["skip-forward"] || [])[0], back = (deck.keys["skip-back"] || [])[0];
    if (fwd || back) { // two quick presses of a skip key (spec 7.6)
      const kbds = [fwd, back].filter(Boolean).map((k) => `<kbd>${esc(keyName(k))}</kbd>`).join("");
      const ends = [fwd && "next", back && "previous"].filter(Boolean).join(" or ");
      rows.push(`<li><span class="lt-pp-kbd">${kbds}×2</span><span>${ends} checkpoint (two presses within half a second)</span></li>`);
    }
    rows.push(`<li><span class="lt-pp-kbd"><kbd>1</kbd>…<kbd>9</kbd></span><span>choose a branch option or a detour (slide keys)</span></li>`);
    if (Object.values(deck.instances).some((i) => registry[i.component] && registry[i.component].zoom)) {
      rows.push(`<li><span class="lt-pp-kbd"><kbd>click</kbd></span><span>enlarge a block; any key or click closes it</span></li>`);
    }
    return rows.join("");
  }

  // What NEXT would show: the next step of this slide, else the slide NEXT moves to, at the step it lands on.
  function previewTarget() {
    const s = slide(nav.cur.slide);
    if (nav.cur.step < s.steps - 1) {
      const d = stepDetour(nav.cur.slide, nav.cur.step + 1);
      if (d) return { slide: deck.detours[d.id].entry, step: 0, label: `detour: ${deck.detours[d.id].label}` };
      return { slide: nav.cur.slide, step: nav.cur.step + 1, label: `step ${nav.cur.step + 2} of ${s.steps}` };
    }
    const nt = nextTarget();
    if (!nt || !nt.slide) return { slide: null, label: s.branches.length ? "choose a branch" : "end of path" };
    if (nt.kind === "back") {
      const i = topExcursion();
      return { slide: nt.slide, step: i >= 0 ? nav.H[i].step : steps(nt.slide) - 1, label: `return to ${label(nt.slide)}` };
    }
    return { slide: nt.slide, step: 0, label: label(nt.slide) };
  }

  function updatePreview() {
    if (!previewFrame) return;
    const t = previewTarget();
    $(".lt-pp-next-label").textContent = t.label ? `\u00b7 ${t.label}` : "";
    const none = $(".lt-pp-next-none");
    none.hidden = !!t.slide;
    none.textContent = t.slide ? "" : t.label;
    previewFrame.style.visibility = t.slide ? "visible" : "hidden";
    if (previewReady && t.slide) previewFrame.contentWindow.postMessage({ lattice: "preview", slide: t.slide, step: t.step }, "*");
  }

  function updatePresenter() {
    const panel = $("#lt-presenter-panel");
    const s = slide(nav.cur.slide);
    const nt = nextTarget();
    const moves = [];
    const sd = nav.cur.step < s.steps - 1 ? stepDetour(nav.cur.slide, nav.cur.step + 1) : null;
    if (sd) {
      moves.push(`<li><kbd>\u2192</kbd> detour: ${esc(deck.detours[sd.id].label)}${sd.blocking ? " (blocking)" : ""}</li>`);
      const sk = (deck.keys["skip-detour"] || [])[0];
      if (sk) moves.push(`<li><kbd>${esc(keyName(sk))}</kbd> skip the detour step</li>`);
    }
    else if (nav.cur.step < s.steps - 1) moves.push(`<li><kbd>\u2192</kbd> step ${nav.cur.step + 2} of ${s.steps}</li>`);
    else if (nt && nt.slide) moves.push(`<li><kbd>\u2192</kbd> ${nt.kind === "back" ? "return to " : ""}${esc(label(nt.slide))}</li>`);
    else moves.push(`<li><kbd>\u2192</kbd> end of path</li>`);
    for (const b of s.branches) moves.push(`<li><kbd>${esc(b.key)}</kbd> ${esc(b.label || label(b.target))}</li>`);
    s.detours.forEach((dId, i) => {
      const d = deck.detours[dId];
      moves.push(`<li><kbd>${esc(d.key || (i === 0 ? "\u2193" : "?"))}</kbd> detour: ${esc(d.label)}</li>`);
    });
    const rt = returnTarget();
    if (rt && (topExcursion() >= 0 || detourOf(nav.cur.slide))) moves.push(`<li><kbd>\u2191</kbd> return to ${esc(label(rt))}</li>`);
    $(".lt-pp-where", panel).textContent = `${s.label} \u00b7 step ${nav.cur.step + 1}/${s.steps}`;
    const scrub = $(".lt-pp-scrub", panel);
    scrub.hidden = s.steps < 2;
    const range = $("input", scrub);
    range.max = String(Math.max(1, s.steps - 1));
    range.value = String(nav.cur.step);
    $(".lt-pp-scrub-label", scrub).textContent = `${nav.cur.step + 1} / ${s.steps}`;
    $(".lt-pp-moves", panel).innerHTML = moves.join("");
    const notes = $(".lt-pp-notes", panel);
    notes.innerHTML = s.notes || "<p class=\"lt-muted\">No notes for this slide.</p>";
    renderMath(notes);
    updatePreview();
    tickTimer();
  }
  function tickTimer() {
    const el = $(".lt-pp-timer");
    if (!el) return;
    const secs = Math.floor((Date.now() - timerStart) / 1000);
    el.textContent = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
  }

  function renderMath(root) {
    if (!window.katex) return;
    for (const el of $$(".lt-math", root)) {
      if (el.dataset.done) continue;
      try {
        window.katex.render(el.textContent, el, { displayMode: el.dataset.display === "1", throwOnError: false });
        el.dataset.done = "1";
      } catch (e) { console.error(e); }
    }
  }

  // ------------------------------------------------------------------ print (spec 11.5)
  // Each page of the plan is rendered, then its slide is copied into a static page. Chromium prints
  // the copies in one pass, so links between pages become links inside the PDF.
  const nextFrame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function renameIds(root, suffix) {
    const ids = new Map();
    for (const el of [root, ...$$("[id]", root)]) {
      if (!el.id) continue;
      ids.set(el.id, el.id + suffix);
      el.id += suffix;
    }
    const fix = (v) => v.replace(/url\(\s*(['"]?)#([^)'"]+)\1\s*\)/g, (m, q, id) => (ids.has(id) ? `url(#${ids.get(id)})` : m));
    for (const el of [root, ...$$("*", root)]) {
      for (const a of Array.from(el.attributes)) {
        if (!a.value.includes("#")) continue;
        let v = fix(a.value);
        if ((a.name === "href" || a.name === "xlink:href") && v.startsWith("#") && ids.has(v.slice(1))) v = `#${ids.get(v.slice(1))}`;
        if (v !== a.value) el.setAttribute(a.name, v);
      }
    }
  }

  function pageLink(el, page, extra) {
    const a = document.createElement("a");
    for (const at of Array.from(el.attributes)) if (!at.name.startsWith("data-") && at.name !== "type") a.setAttribute(at.name, at.value);
    a.innerHTML = el.innerHTML + (extra || "");
    if (page) a.href = `#lt-page-${page}`;
    else a.classList.add("lt-print-nolink");
    el.replaceWith(a);
  }

  function snapshot(entry, plan) {
    const sec = sections[entry.slide];
    const clone = sec.cloneNode(true);
    clone.hidden = false;
    // a copy does not keep scroll positions (a code block scrolled to its highlight): note them now, while
    // the copy still has the original's structure, and restore them once the copy is in the document
    const copies = $$("*", clone);
    const scrolled = $$("*", sec).map((e, i) => [copies[i], e.scrollTop, e.scrollLeft]).filter(([, t, l]) => t || l);
    clone.classList.remove(...Array.from(clone.classList).filter((c) => c.startsWith("lt-anim-")));
    const src = $$("canvas", sec);
    $$("canvas", clone).forEach((c, i) => {
      try {
        const img = document.createElement("img");
        img.src = src[i].toDataURL("image/png");
        img.style.cssText = c.style.cssText;
        img.style.width = `${src[i].clientWidth}px`;
        img.style.height = `${src[i].clientHeight}px`;
        c.replaceWith(img);
      } catch (e) { console.error(e); }
    });
    renameIds(clone, `-p${entry.n}`);
    const ref = (page) => (page ? `<span class="lt-print-ref">p.\u00a0${page}</span>` : "");
    for (const a of $$("a[data-lt-link]", clone)) {
      const t = resolveTarget(a.dataset.ltLink);
      const page = t && plan.pageOf[t];
      if (page) a.setAttribute("href", `#lt-page-${page}`);
      else { a.removeAttribute("href"); a.classList.add("lt-print-nolink"); }
    }
    for (const b of $$("[data-lt-detour]", clone)) {
      const d = deck.detours[b.dataset.ltDetour];
      const page = d && plan.pageOf[d.entry];
      pageLink(b, page, ref(page));
    }
    const s = slide(entry.slide);
    for (const b of $$("[data-lt-choose]", clone)) {
      const opt = s.branches.find((o) => o.key === b.dataset.ltChoose);
      const page = opt && plan.pageOf[opt.target];
      pageLink(b, page, ref(page));
    }
    const page = document.createElement("div");
    page.className = "lt-print-page";
    page.id = `lt-page-${entry.n}`;
    page.appendChild(clone);
    page.ltScrolled = scrolled;
    const sec2 = entry.section != null ? plan.sections[entry.section] : null;
    let where = esc(plan.title);
    if (sec2) {
      where = `Appendix ${esc(sec2.code)} \u00b7 ${esc(sec2.title)}`;
      if (entry.from) where += ` \u00b7 <a href="#lt-page-${entry.from}">from p.\u00a0${entry.from}</a>`;
    }
    const stepInfo = s.steps > 1 ? ` \u00b7 step ${entry.step + 1}/${s.steps}` : "";
    page.insertAdjacentHTML("beforeend",
      `<div class="lt-print-foot"><span>${where}</span><span>${esc(s.label)}${stepInfo}<b>${entry.n}</b></span></div>`);
    return page;
  }

  async function print(plan) {
    const holder = document.createElement("div");
    holder.id = "lt-print-pages";
    document.body.appendChild(holder);
    for (const entry of plan.pages) {
      const prev = Object.assign({}, nav.cur);
      nav.cur = { slide: entry.slide, step: Math.max(0, Math.min(entry.step, steps(entry.slide) - 1)) };
      render(prev, { kind: "sync", dir: 0 });
      await nextFrame();
      if (prev.slide !== entry.slide && (instancesBySlide[entry.slide] || []).length) await sleep(120); // async renderers (Vega)
      const page = snapshot(entry, plan);
      holder.appendChild(page);
      for (const [e, top, left] of page.ltScrolled) { e.scrollTop = top; e.scrollLeft = left; }
    }
    $("#lt-root").hidden = true;
    document.documentElement.classList.add("lt-printed");
    return plan.pages.length;
  }

  // ------------------------------------------------------------------ input
  function keyMap() {
    const m = {};
    for (const [action, keys] of Object.entries(deck.keys)) for (const k of keys) m[k] = action;
    return m;
  }

  function onKey(e) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    if (zoomed) { // any key closes an enlarged element instead of acting (spec 7.7)
      if (!MODIFIERS.has(e.key)) { closeZoom(); e.preventDefault(); }
      return;
    }
    if (e.target && e.target.closest && e.target.closest("input, textarea, select")) return;
    if (overlayOpen()) {
      if (e.key === "Escape" || (e.key === "o" && $(".lt-overview"))) { closeOverlay(); e.preventDefault(); }
      return;
    }
    const s = slide(nav.cur.slide);
    const slideKey = s.branches.some((b) => b.key === e.key) || s.detours.some((d) => deck.detours[d].key === e.key);
    if (slideKey) { stopPlaying(); burstMove(null, e); actions.choose(e.key); e.preventDefault(); return; }
    // Bindings may name a shifted key as "Shift+ArrowRight"; a plain key still matches with Shift held
    // (letters already arrive shifted, as "A" for Shift+a).
    const map = keyMap();
    const action = (e.shiftKey && map[`Shift+${e.key}`]) || map[e.key];
    if (action && actions[action]) {
      const move = burstMove(action, e); // before stopPlaying: it reads the playback under way
      stopPlaying();
      if (move === null) actions[action](); else playSteps(move.target, move);
      e.preventDefault();
    }
  }

  // Two presses of `skip-forward` within half a second play to the next checkpoint (spec 6.5), two of
  // `skip-back` to the previous one (spec 7.6). The checkpoint is counted from the anchor: the step before
  // the first press, or the target of a checkpoint playback still under way in the same direction. The
  // first press plays its ten steps from the anchor, but waits at that checkpoint while the window is
  // open, so that a second press never has to play back. Later presses in the window keep the target.
  // The auto-repeat of a held key does not count, and any other action starts the count again.
  // Returns null for the plain action, or the arguments of playSteps: { target, hold, checkpoint }.
  const BURST = {
    "skip-forward": { dir: 1, checkpoint: nextCheckpoint, plain: (id, s) => Math.min(s + 10, steps(id) - 1) },
    "skip-back": { dir: -1, checkpoint: prevCheckpoint, plain: (id, s) => Math.max(s - 10, 0) },
  };
  const BURST_WINDOW_MS = 500;
  let burst = { action: null };
  function burstMove(action, e) {
    const b = BURST[action];
    if (!b) { burst = { action: null }; return null; }
    if (e.repeat) return null;
    const now = performance.now();
    const id = nav.cur.slide;
    if (burst.action === action && burst.slide === id && now - burst.start < BURST_WINDOW_MS) {
      return { target: burst.target, checkpoint: true }; // the second press, or a later one in the window
    }
    const run = playing && playing.checkpoint && playing.slide === id && playing.dir === b.dir;
    const anchor = run ? playing.target : nav.cur.step;
    burst = { action, slide: id, start: now, target: b.checkpoint(id, anchor) };
    return { target: b.plain(id, anchor), hold: { step: burst.target, until: now + BURST_WINDOW_MS } };
  }

  function onClick(e) {
    const jump = e.target.closest("[data-jump]");
    if (jump) { e.preventDefault(); closeOverlay(); actions.jump(jump.dataset.jump); return; }
    const link = e.target.closest("[data-lt-link]");
    if (link) { e.preventDefault(); actions.jump(link.dataset.ltLink); return; }
    const choose = e.target.closest("[data-lt-choose]");
    if (choose) { e.preventDefault(); actions.choose(choose.dataset.ltChoose); return; }
    const detour = e.target.closest("[data-lt-detour]");
    if (detour) { e.preventDefault(); actions.enter(detour.dataset.ltDetour); return; }
    if (e.target.closest(".lt-pp-timer")) { timerStart = Date.now(); tickTimer(); return; }
    if (e.target.id === "lt-overlay") closeOverlay();
  }

  // ------------------------------------------------------------------ layout
  function fit() {
    const stage = $("#lt-stage");
    const vp = $("#lt-viewport");
    const W = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--lt-w"));
    const H = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--lt-h"));
    const r = stage.getBoundingClientRect();
    const scale = Math.min(r.width / W, r.height / H);
    vp.style.transform = `translate(${(r.width - W * scale) / 2}px, ${(r.height - H * scale) / 2}px) scale(${scale})`;
    if (zoomed) placeCard(zoomed.card, zoomBox(zoomed.size));
    for (const cb of resizeCallbacks) try { cb(scale); } catch (e) { console.error(e); }
  }

  // ------------------------------------------------------------------ boot
  async function loadData() {
    const pending = Object.entries(deck.instances).filter(([, m]) => m.url);
    await Promise.all(pending.map(async ([id, m]) => {
      try {
        const r = await fetch(m.url);
        dataStore[id] = await r.json();
      } catch (err) {
        console.error(`lattice: cannot load ${m.url} (directory output must be served over HTTP)`, err);
      }
    }));
  }

  function bootPassive() {
    // A passive window renders what it is told: the presenter's preview pane, or the PDF export.
    nav = { cur: { slide: deck.start, step: 0 }, H: [], tour: null };
    fit();
    render(null, { kind: "sync", dir: 0 });
    if (printing) return;
    window.addEventListener("message", (e) => {
      const m = e.data;
      if (e.source !== window.parent || !m || m.lattice !== "preview" || !deck.slides[m.slide]) return;
      const prev = Object.assign({}, nav.cur);
      nav.cur = { slide: m.slide, step: Math.max(0, Math.min(m.step || 0, steps(m.slide) - 1)) };
      render(prev, { kind: "sync", dir: 0 });
    });
    if (window.parent !== window) window.parent.postMessage({ lattice: "preview-ready" }, "*");
  }

  async function boot() {
    deck = JSON.parse($("#lt-deck").textContent);
    await loadData();
    const params = new URLSearchParams(location.search);
    printing = params.has("print");
    passive = printing || params.has("preview");
    presenter = !passive && params.has("presenter");
    storageKey = `lattice:${deck.hash}:nav`;
    for (const sec of $$(".lt-slide")) sections[sec.dataset.slide] = sec;
    for (const [id, inst] of Object.entries(deck.instances)) (instancesBySlide[inst.slide] ||= []).push(id);
    renderMath(document);
    window.addEventListener("resize", fit);
    window.addEventListener("pagehide", () => {
      for (const m of Object.values(mounted)) {
        if (m.ctl.destroy) try { m.ctl.destroy(m.inst); } catch (e) { console.error(e); }
      }
    });
    if (passive) {
      document.documentElement.classList.add(printing ? "lt-print" : "lt-preview");
      bootPassive();
      document.documentElement.classList.add("lt-ready");
      return;
    }
    if (presenter) {
      document.body.classList.add("lt-presenter");
      $("#lt-presenter-panel").hidden = false;
      buildPresenter();
      setInterval(tickTimer, 1000);
    }
    nav = restore();
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onZoomPointer, true);
    document.addEventListener("mousedown", onZoomPointer, true);
    document.addEventListener("click", onZoomClick, true);
    document.addEventListener("click", onClick);
    window.addEventListener("hashchange", () => {
      const h = parseHash();
      if (h && (h.slide !== nav.cur.slide || h.step !== nav.cur.step)) {
        if (h.slide === nav.cur.slide) go(h.slide, h.step, { kind: "hash", dir: 0 }); // a jump: never animates
        else { push("excursion"); go(h.slide, h.step, { kind: "link", dir: 1 }); }
      }
    });
    if ("BroadcastChannel" in window) {
      channel = new BroadcastChannel(`lattice:${deck.hash}`);
      channel.onmessage = (e) => onRemote(e.data);
    }
    fit();
    render(null, { kind: "sync", dir: 0 });
    document.documentElement.classList.add("lt-ready");
  }

  return { component, boot, frames, applyDelta, renderPanel, esc, print, actions: () => actions, state: () => nav,
    zoomed: () => (zoomed ? { instance: zoomed.instance, key: zoomed.key } : null) };
})();
window.Lattice = Lattice;
