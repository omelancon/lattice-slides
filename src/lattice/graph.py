"""Graph resolution and structural validation (spec section 5)."""
from __future__ import annotations

from collections import deque

from .model import DEFAULT_KEYS, Deck, Edge, Slide


def resolve_target(deck: Deck, ident: str) -> str | None:
    """Resolve a slide or detour id to a slide id."""
    if ident in deck.slides:
        return ident
    d = deck.detours.get(ident)
    if d is not None and d.slides:
        return d.slides[0].id
    return None


def resolve_graph(deck: Deck) -> None:
    diags = deck.diagnostics
    seqs: dict[str, list[Slide]] = {}
    for s in deck.slides.values():
        seqs.setdefault(s.scope_id, []).append(s)

    # -- next (5.2)
    for s in deck.slides.values():
        spec = s.next_spec
        if spec == "back":
            s.next = "back"
        elif spec == "none":
            s.next = None
        elif spec is not None:
            t = resolve_target(deck, spec)
            if t is None:
                diags.error("LT012", f"next target {spec!r} does not exist", s.loc)
                s.next = None
            elif s.scope is not None and deck.slides[t].scope_id != s.scope_id:
                diags.error("LT013", f"next target {spec!r} is outside detour {s.scope_id!r}", s.loc)
                s.next = None
            else:
                s.next = t
        elif s.branch is not None:
            s.next = None
        elif s.offpath:
            s.next = "back"
        else:
            seq = seqs[s.scope_id]
            i = seq.index(s)
            nxt = next((x for x in seq[i + 1:] if not x.offpath), None)
            if nxt is not None:
                s.next = nxt.id
            else:
                s.next = None if s.scope is None else "back"

    # -- edges (5.3)
    edges: list[Edge] = []
    for s in deck.slides.values():
        if s.next not in (None, "back"):
            edges.append(Edge(s.id, s.next, "next", implicit=s.next_spec is None))
        if s.branch is not None:
            for o in s.branch.options:
                t = resolve_target(deck, o.target)
                if t is None:
                    diags.error("LT011", f"branch target {o.target!r} does not exist", o.loc)
                    continue
                if deck.slides[t].scope_id != s.scope_id:
                    diags.error("LT013", f"branch target {o.target!r} is outside the slide's scope", o.loc)
                    continue
                edges.append(Edge(s.id, t, "branch", key=o.key))
        for d in s.detours:
            if d.slides:
                edges.append(Edge(s.id, d.slides[0].id, "detour", key=d.key))
        for target in s.links:
            t = resolve_target(deck, target)
            if t is None:
                diags.error("LT011", f"link to unknown id {target!r}", s.loc)
                continue
            edges.append(Edge(s.id, t, "link"))
    deck.edges = edges

    # -- keys (3.11)
    global_keys = set()
    bindings = dict(DEFAULT_KEYS)
    for action, keys in deck.meta.keys.items():
        bindings[action] = [keys] if isinstance(keys, str) else list(keys)
    for keys in bindings.values():
        global_keys.update(keys)
    for s in deck.slides.values():
        seen: set[str] = set()
        keyed = [(o.key, o.loc) for o in (s.branch.options if s.branch else [])]
        keyed += [(d.key, d.loc) for d in s.detours]
        for key, loc in keyed:
            if key is None:
                continue
            if key in seen:
                diags.error("LT018", f"key {key!r} used twice on slide {s.id!r}", loc)
            if key in global_keys:
                diags.error("LT018", f"key {key!r} collides with a global binding", loc)
            seen.add(key)

    # -- start and main path (5.4)
    if deck.meta.start:
        start = resolve_target(deck, deck.meta.start)
        if start is None:
            diags.error("LT012", f"start slide {deck.meta.start!r} does not exist")
    else:
        start = next((s.id for s in deck.slides.values() if s.scope is None and not s.offpath), None)
        if start is None:
            diags.error("LT042", "the deck has no start slide")
    deck.start = start or ""
    path, seen_ids = [], set()
    cur = start
    while cur not in (None, "back") and cur in deck.slides:
        if cur in seen_ids:
            diags.error("LT014", f"cycle on the main path at slide {cur!r}", deck.slides[cur].loc)
            break
        seen_ids.add(cur)
        path.append(cur)
        cur = deck.slides[cur].next
    deck.main_path = path

    # -- detour termination (5.5)
    for d in deck.detours.values():
        if not d.slides:
            continue
        cur, visited = d.slides[0].id, set()
        while True:
            if cur == "back":
                break
            if cur is None or cur in visited:
                diags.error("LT035", f"detour {d.id!r} does not end with a return", d.loc)
                break
            visited.add(cur)
            cur = deck.slides[cur].next

    # -- reachability (5.6)
    if start:
        adj: dict[str, list[str]] = {}
        for e in edges:
            adj.setdefault(e.source, []).append(e.target)
        reach, queue = {start}, deque([start])
        while queue:
            for t in adj.get(queue.popleft(), []):
                if t not in reach:
                    reach.add(t)
                    queue.append(t)
        for s in deck.slides.values():
            if s.id not in reach:
                diags.warn("LT015", f"slide {s.id!r} is unreachable from the start slide", s.loc)

    # -- tours (5.7)
    for name, spec in deck.meta.tours.items():
        if spec == "main":
            deck.tours[name] = list(deck.main_path)
            continue
        ids: list[str] = []
        for ident in spec:
            if ident in deck.detours:
                d = deck.detours[ident]
                cur = d.slides[0].id if d.slides else None
                while cur not in (None, "back"):
                    ids.append(cur)
                    cur = deck.slides[cur].next
            elif ident in deck.slides:
                ids.append(ident)
            else:
                diags.error("LT012", f"tour {name!r} references unknown id {ident!r}")
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            diags.error("LT043", f"tour {name!r} repeats slides: {', '.join(sorted(dup))}")
        deck.tours[name] = ids
