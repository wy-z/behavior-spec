"""Mermaid diagram derivation — flow pipelines and module context graphs.

Diagrams are DERIVED from existing structured fields, never authored and never
stored, so they cannot drift from the normative content (a diagram that
contradicts the rule would be worse than none). One mermaid string feeds both
surfaces: `termaid` renders it in the review TUI, and a ```mermaid``` fence
renders it on GitHub / in `bspec doc` output.

Only flow and module get diagrams. A behavior's `then` clauses are ANDed
obligations — drawing them as a graph would imply an ordering the spec does not
have; its WHEN/MUST card is the faithful view. An invariant is a single
predicate. Neither earns a diagram.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model import Project, Symbol

_LABEL_CAP = 60


@dataclass(frozen=True)
class IOEdge:
    """One event crossing a module boundary, with the interface it crosses."""
    direction: str  # "input" (into the module) | "output" (out of it)
    interface: str
    event: str


def _label(text: str) -> str:
    """Mermaid-safe label: collapse whitespace, neutralize the characters that
    delimit nodes/edges, and cap runaway length (renderers wrap the rest)."""
    s = " ".join((text or "").split())
    s = s.replace('"', "'").replace("|", "/").replace("[", "(").replace("]", ")")
    s = s.replace("<", "(").replace(">", ")")  # also kills stray <br/> etc.
    if len(s) > _LABEL_CAP:
        s = s[: _LABEL_CAP - 1] + "…"
    return s


def _nid(prefix: str, raw: str) -> str:
    """Mermaid-safe node id (alphanumerics + underscore only)."""
    return prefix + re.sub(r"[^0-9A-Za-z]", "_", raw)


def flow_mermaid(proj: Project, flow: Symbol) -> str:
    """Ordered step pipeline. Nodes are keyed by position, not behavior id, so a
    repeated step can never fold the chain into a cycle. Arrows mean *ordered
    after*, never *data flows to* — flows declare no data passing between steps."""
    steps = flow.obj.get("steps", [])
    if not steps:
        return ""
    lines = ["flowchart TD"]
    prev = None
    for i, bid in enumerate(steps, 1):
        b = proj.get("behavior", bid)
        label = (b.obj.get("name") or bid) if b else bid
        nid = f"s{i}"
        lines.append(f'  {nid}["{_label(label)}"]')
        if prev is not None:
            lines.append(f"  {prev} --> {nid}")
        prev = nid
    return "\n".join(lines)


def module_io(proj: Project, module: Symbol) -> list[IOEdge]:
    """The events crossing a module's boundary (its file's events), each with its
    interface and direction. Shared source for the mermaid graph and the TUI
    I/O table, sorted by id so output is deterministic."""
    out: list[IOEdge] = []
    events = sorted(
        (e for e in proj.kind("event").values() if e.file == module.file),
        key=lambda e: e.id,
    )
    for ev in events:
        iface = ev.obj.get("interface")
        if iface:
            out.append(IOEdge(ev.obj.get("direction") or "input", iface, ev.id))
    return out


def module_mermaid(proj: Project, module: Symbol) -> str:
    """Context / data-flow graph: input interfaces feed the module, the module
    feeds output interfaces, each edge labelled with the event that crosses it.
    A module with no events renders as a lone black-box node. (Wide in a terminal
    — the TUI uses module_io as a table instead; this feeds GitHub/`bspec doc`.)"""
    lines = ["flowchart LR", f'  mod["{_label(module.id)}"]']
    seen: dict[str, str] = {}  # interface id -> node id
    edges: list[str] = []
    for e in module_io(proj, module):
        if e.interface not in seen:
            nid = _nid("if_", e.interface)
            seen[e.interface] = nid
            iface = proj.get("interface", e.interface)
            lines.append(f'  {nid}(["{_label((iface.obj.get("name") or e.interface) if iface else e.interface)}"])')
        nid = seen[e.interface]
        ev = proj.get("event", e.event)
        elabel = _label((ev.obj.get("name") or e.event) if ev else e.event)
        if e.direction == "output":
            edges.append(f'  mod -->|"{elabel}"| {nid}')
        else:
            edges.append(f'  {nid} -->|"{elabel}"| mod')
    return "\n".join(lines + edges)
