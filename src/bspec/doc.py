"""Markdown + mermaid export — a shareable, diagram-rich rendering of a module.

Diagrams are the same mermaid `diagram.py` derives for the TUI, here placed in
```mermaid``` fences so GitHub / VS Code render them. The wide module context
graph, which a terminal can't fit, renders fine as SVG on those surfaces.
Behaviours and invariants show their faithful rule text — by design they have no
diagram. CEL goes in inline code, where `<`, `>`, `&&` render literally with no
escaping.
"""

from __future__ import annotations

from . import diagram
from .model import Project


def _cel(node) -> str:
    return node.get("cel", "") if isinstance(node, dict) else ""


def _fence(mermaid: str) -> list[str]:
    return ["```mermaid", mermaid, "```", ""] if mermaid else []


def _behavior_rules(o: dict) -> list[str]:
    lines: list[str] = []
    if "given" in o:
        lines.append(f"- **GIVEN** `{_cel(o['given'])}`")
    w = o.get("when", {})
    when = f"- **WHEN** `{w.get('event', '')}`"
    if _cel(w.get("where")):
        when += f" where `{_cel(w['where'])}`"
    lines.append(when)
    for entry in o.get("then", []):
        if "assert" in entry:
            lines.append(f"- **MUST** assert `{_cel(entry['assert'])}`")
        elif "emit" in entry:
            e = entry["emit"]
            s = f"- **MUST** emit `{e.get('event', '')}`"
            if _cel(e.get("where")):
                s += f" where `{_cel(e['where'])}`"
            lines.append(s)
        elif "forbid" in entry:
            lines.append(f"- **MUST NOT** emit `{entry['forbid'].get('event', '')}`")
    return lines


def _invariant_rules(o: dict) -> list[str]:
    lines: list[str] = []
    if "while" in o:
        lines.append(f"- **WHILE** `{_cel(o['while'])}`")
    lines.append(f"- **ASSERT** `{_cel(o.get('assert'))}`")
    return lines


def _origin(o: dict) -> list[str]:
    locs = [org.get("uri", "") for org in o.get("origin", [])]
    return [f"_origin: {', '.join(locs)}_", ""] if locs else []


def _heading(prefix: str, o: dict, oid: str) -> list[str]:
    out = [f"{prefix} {o.get('name') or oid}", "", f"`{oid}`", ""]
    if o.get("title"):
        out += [f"> **{o['title']}**", ""]
    if o.get("rationale"):
        out += [o["rationale"], ""]
    return out


def _unit(proj: Project, kind: str, oid: str, rules) -> list[str]:
    o = proj.get(kind, oid).obj
    out = _heading("###", o, oid)
    out += rules(o) + [""]
    out += _origin(o)
    return out


def _module_md(proj: Project, mid: str) -> list[str]:
    m = proj.get("module", mid)
    out = _heading("#", m.obj, mid)
    out += _fence(diagram.module_mermaid(proj, m))

    gloss = proj.glossary.get(mid, {})
    if gloss:
        out += ["## Glossary", ""]
        out += [f"- **{t}** — {d}" for t, d in gloss.items()]
        out += [""]

    members = proj.module_members(mid)

    if members["flow"]:
        out += ["## Flows", ""]
        for fid in members["flow"]:
            f = proj.get("flow", fid)
            out += _heading("###", f.obj, fid)
            out += _fence(diagram.flow_mermaid(proj, f))

    if members["behavior"]:
        out += ["## Behaviors", ""]
        for bid in members["behavior"]:
            out += _unit(proj, "behavior", bid, _behavior_rules)

    if members["invariant"]:
        out += ["## Invariants", ""]
        for iid in members["invariant"]:
            out += _unit(proj, "invariant", iid, _invariant_rules)

    return out


def render(proj: Project, module_id: str | None = None) -> str:
    mids = [module_id] if module_id else sorted(proj.kind("module"))
    blocks = ["\n".join(_module_md(proj, mid)) for mid in mids if proj.get("module", mid)]
    return "\n\n---\n\n".join(blocks).rstrip() + "\n"
