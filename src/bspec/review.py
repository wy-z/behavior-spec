"""Interactive review — the ONLY writer of the review-state file (bspec.json).

The Agent never writes review records; only this module does, and only from an
explicit human decision. Rendering uses `rich`; the verdict/loop logic stays
plain stdlib so piped input keeps working.
"""

from __future__ import annotations

import datetime as _dt
import json
import os

import termaid
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import diagram, expression, status
from .model import REVIEW_STATE_FILENAME, Project

_DECISIONS = {"a": "approved", "c": "changes_requested", "r": "rejected", "d": "deferred"}


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def record_decision(root: str, key: str, decision: str, sem_hash: str,
                    comment: str | None = None) -> None:
    """Write a single review decision into the review-state file (create if absent)."""
    state = status.load_review_state(root)
    state.setdefault("version", "0.1.0")
    state.setdefault("lang", "en")
    state.setdefault("specGlobs", ["**/*.bspec.json"])
    rec = {
        "semanticHash": sem_hash,
        "decision": decision,
        "reviewedAt": _now(),
    }
    if comment:
        rec["comment"] = comment
    state.setdefault("reviews", {})[key] = rec
    path = os.path.join(root, REVIEW_STATE_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


# --------------------------------------------------------------------------- #
# rendering (rich)
# --------------------------------------------------------------------------- #
_STATUS_STYLE = {
    "pending": "yellow", "approved": "green", "changes_requested": "magenta",
    "rejected": "red", "deferred": "blue", "stale": "red",
}


def _cel(node) -> str:
    return node.get("cel", "") if isinstance(node, dict) else ""


def _badge(stat: str) -> Text:
    return Text(f" {stat} ", style=f"reverse {_STATUS_STYLE.get(stat, 'white')}")


def _typed_name(kind: str, obj: dict, oid: str, labels: dict) -> str:
    """`[kind][direction] readable-name`. The tag is the object's raw kind +
    direction/role, prepended at display time so a reviewer always sees *what a
    unit is*. `labels` (authored once in bspec.json `typeLabels`) localizes each
    token if present; the tool never translates, only looks up. `name` is the
    authored readable label."""
    def tok(t: str) -> str:
        return labels.get(t, t)
    tag = f"[{tok(kind)}]"
    sub = obj.get("direction") or (obj.get("role") if kind == "observable" else "")
    if sub:
        tag += f"[{tok(sub)}]"
    return f"{tag} {obj.get('name') or oid}"


def _event_text(prefix: str, event: str | None, where) -> Text:
    """`<prefix><event>  where <cel>` with event in yellow and CEL in green."""
    parts: list = []
    if prefix:
        parts.append((prefix, "dim"))
    parts.append((event or "", "yellow"))
    if where and _cel(where):
        parts.append(("  where ", "dim"))
        parts.append((_cel(where), "green"))
    return Text.assemble(*parts)


def _section(header: bool = False, lines: bool = False) -> Table:
    """A bordered section table — `expand=False` hugs content; the rounded border
    draws the table lines. The section's title is rendered above it by `_titled`."""
    return Table(box=box.ROUNDED, border_style="dim", show_header=header,
                 header_style="bold dim", show_lines=lines, expand=False, padding=(0, 1))


def _titled(label: str, widget):
    """One uniform section: a left header line + the widget + a trailing blank.
    Every section (why / I/O / flow / units / glossary / rule / referenced) reads
    the same — header above the box, never on its border."""
    if widget is None:
        return None
    return Group(Text(label, style="dim"), widget, Text(""))


def _rule_table(kind: str, sym):
    o = sym.obj
    t = _section(lines=True)
    t.add_column(style="bold cyan", justify="right", no_wrap=True)
    t.add_column(overflow="fold")
    if kind == "behavior":
        if "given" in o:
            t.add_row("GIVEN", Text(_cel(o["given"]), style="green"))
        w = o.get("when", {})
        t.add_row("WHEN", _event_text("", w.get("event"), w.get("where")))
        for entry in o.get("then", []):
            if "assert" in entry:
                t.add_row("MUST", Text.assemble(("assert ", "dim"), (_cel(entry["assert"]), "green")))
            elif "emit" in entry:
                t.add_row("MUST", _event_text("emit ", entry["emit"].get("event"), entry["emit"].get("where")))
            elif "forbid" in entry:
                t.add_row("MUST", _event_text("forbid ", entry["forbid"].get("event"), None))
    else:  # invariant
        if "while" in o:
            t.add_row("WHILE", Text(_cel(o["while"]), style="green"))
        t.add_row("ASSERT", Text(_cel(o.get("assert")), style="green"))
    return _titled("Rule", t)


def _refs_table(proj: Project, sym, kind: str, labels: dict):
    """Referenced observables/events with their typed names."""
    t = _section(lines=True)
    t.add_column(overflow="fold")
    t.add_column(style="dim", no_wrap=True)
    rows = 0
    for oid in sorted(expression.referenced_observables(proj, sym, kind)):
        s = proj.get("observable", oid)
        if s:
            t.add_row(Text(_typed_name("observable", s.obj, oid, labels)), oid)
            rows += 1
    if kind == "behavior":
        eids = []
        if sym.obj.get("when", {}).get("event"):
            eids.append(sym.obj["when"]["event"])
        for entry in sym.obj.get("then", []):
            for k in ("emit", "forbid"):
                if k in entry and entry[k].get("event"):
                    eids.append(entry[k]["event"])
        for eid in eids:
            s = proj.get("event", eid)
            if s:
                t.add_row(Text(_typed_name("event", s.obj, eid, labels)), eid)
                rows += 1
    return _titled("Referenced", t) if rows else None


def _glossary_table(proj: Project, kind: str, oid: str):
    mid = oid if kind == "module" else proj.membership.get((kind, oid))
    gloss = proj.glossary.get(mid, {})
    if not gloss:
        return None
    t = _section(lines=True)
    t.add_column(style="bold", no_wrap=True)
    t.add_column(overflow="fold", style="dim")
    for term, defn in gloss.items():
        t.add_row(term, defn)
    return _titled("Glossary", t)


def _flow_box(proj: Project, fid: str):
    """A flow's pipeline diagram, the flow id on its border (so multiple flows in a
    module are each labelled). The section header 'flow' is added by the caller."""
    mermaid = diagram.flow_mermaid(proj, proj.get("flow", fid))
    if not mermaid:
        return None
    try:
        art = termaid.render(mermaid)
    except Exception:
        return None  # a render failure must never break review
    return Panel(Text(art, no_wrap=True), title=f"[dim]{fid}[/]", title_align="left",
                 border_style="dim", box=box.ROUNDED, padding=(0, 1), expand=False)


def _io_table(proj: Project, oid: str, labels: dict):
    """Compact boundary I/O for a module: which events enter and leave, via which
    interface. Stands in for the (wide) mermaid context graph inside the terminal;
    `bspec doc` emits that graph for GitHub. Both derive from diagram.module_io."""
    edges = diagram.module_io(proj, proj.get("module", oid))
    if not edges:
        return None
    t = _section(lines=True)
    t.add_column(style="dim", no_wrap=True)
    t.add_column(style="cyan", overflow="fold")
    t.add_column(style="yellow", overflow="fold")
    for d, arrow in (("input", "in →"), ("output", "out ←")):
        for e in [x for x in edges if x.direction == d]:
            iface, ev = proj.get("interface", e.interface), proj.get("event", e.event)
            iname = _typed_name("interface", iface.obj, e.interface, labels) if iface else e.interface
            ename = _typed_name("event", ev.obj, e.event, labels) if ev else e.event
            t.add_row(arrow, Text(iname), Text(ename))
    return _titled("I/O", t)


def _members_table(proj: Project, oid: str, units: dict, labels: dict):
    members = proj.module_members(oid)
    t = _section(header=True, lines=True)
    t.add_column("status", no_wrap=True)
    t.add_column("name", overflow="fold")
    t.add_column("id", style="dim", no_wrap=True)
    any_row = False
    for mk in ("behavior", "invariant", "flow"):
        for mid in members[mk]:
            any_row = True
            obj = proj.get(mk, mid).obj
            st = units.get(f"{mk}:{mid}", {}).get("status", "pending")
            t.add_row(_badge(st), Text(_typed_name(mk, obj, mid, labels)), mid)
    return _titled("Units", t) if any_row else None


def _card(proj: Project, kind: str, oid: str, info: dict, units: dict | None = None) -> Panel:
    """A self-contained, styled approval card: title, rationale, the rule, and every
    term it relies on (referenced observables/events + glossary)."""
    o = proj.get(kind, oid).obj
    sym = proj.get(kind, oid)
    if units is None:
        units = status.compute(proj)
    # Project-level type-token glossary in bspec.json (e.g. interface→接口); looked
    # up to localize the [kind][direction] tag. Distinct from a module's glossary
    # (domain terms, in *.bspec.json, hashed) — this is cosmetic project config.
    labels = status.load_review_state(proj.root).get("glossary", {})
    body: list = []
    if o.get("title"):
        body.append(Text(o["title"], style="bold"))
        body.append(Text(""))
    if o.get("rationale"):
        # rationale in its own box — the requirement (title) stays the bare headline
        body.append(_titled("Why", Panel(Text(o["rationale"]),
                                         border_style="dim", box=box.ROUNDED, padding=(0, 1))))

    if kind in ("behavior", "invariant"):
        body += [_rule_table(kind, sym), _refs_table(proj, sym, kind, labels)]
    elif kind == "flow":
        box_ = _flow_box(proj, oid)
        if box_ is not None:
            body.append(_titled("Flow", box_))
        else:
            t = _section(lines=True)
            t.add_column(style="yellow", no_wrap=True)
            t.add_column(style="dim", overflow="fold")
            for step in o.get("steps", []):
                st = proj.get("behavior", step)
                t.add_row(step, (st.obj.get("name") or step) if st else "(unknown)")
            body.append(_titled("Steps", t))
    elif kind == "module":
        body.append(_io_table(proj, oid, labels))
        # Reviewing the module is the whole-shape view: pair its boundary I/O with
        # each internal flow's sequence diagram, so both read on one card.
        boxes = [b for b in (_flow_box(proj, fid) for fid in proj.module_members(oid)["flow"]) if b]
        if boxes:
            body.append(_titled("Flow", Group(*boxes)))
        body.append(_members_table(proj, oid, units, labels))

    body.append(_glossary_table(proj, kind, oid))

    origins = o.get("origin", [])
    if origins:
        locs = [org.get("uri", "") for org in origins]
        body.append(Text("origin  " + "   ".join(locs), style="dim"))

    head = Text.assemble((_typed_name(kind, o, oid, labels), "bold white"), (f"  {oid}", "dim"))
    sub = _badge(info["status"])
    if info.get("prior"):
        sub = sub + Text(f"  was {info['prior']}", style="dim")
    return Panel(Group(*[b for b in body if b is not None]), title=head, title_align="left",
                 subtitle=sub, subtitle_align="right",
                 border_style=_STATUS_STYLE.get(info["status"], "white"),
                 box=box.ROUNDED, padding=(1, 2))


# --------------------------------------------------------------------------- #
# interactive loop
# --------------------------------------------------------------------------- #
_ACTIONS = [
    ("a", "approve", "green"), ("c", "changes", "magenta"), ("r", "reject", "red"),
    ("d", "defer", "blue"), ("o", "origin", "cyan"), ("s", "skip", "white"),
    ("q", "quit", "white"),
]


def _action_bar() -> Panel:
    """Toolbar of keycap badges so the keystroke for each action is unmistakable."""
    t = Text()
    for i, (key, label, color) in enumerate(_ACTIONS):
        if i:
            t.append("  ")
        t.append(f" {key} ", style=f"reverse {color}")
        t.append(f" {label}", style=color)
    return Panel(t, box=box.ROUNDED, border_style="dim", padding=(0, 1))


def _select(proj: Project, units: dict, kinds, module, status_filter):
    items = []
    for key, info in units.items():
        kind, oid = key.split(":", 1)
        if kinds and kind not in kinds:
            continue
        if module and proj.membership.get((kind, oid)) != module and not (kind == "module" and oid == module):
            continue
        if status_filter and info["status"] not in status_filter:
            continue
        items.append((kind, oid, info))
    order = {k: i for i, k in enumerate(status.REVIEW_KINDS)}
    items.sort(key=lambda t: (order.get(t[0], 9), t[1]))
    return items


def run_review(proj: Project, kinds=None, module=None, status_filter=None) -> int:
    units = status.compute(proj)
    if status_filter is None:
        status_filter = {"pending", "stale"}
    items = _select(proj, units, kinds, module, status_filter)
    # Cap at a readable column: a review card reads like prose, and on a very wide
    # terminal an unbounded card sprawls (columns spread, diagrams float in space).
    console = Console()
    if console.size.width > 100:
        console = Console(width=100)
    if not items:
        console.print("[dim]Nothing to review for that filter.[/]")
        return 0

    recorded = 0
    for n, (kind, oid, info) in enumerate(items, 1):
        console.print()
        console.rule(f"[dim]{n}/{len(items)}[/]", align="left")
        console.print(_card(proj, kind, oid, info, units))
        console.print(_action_bar())
        try:
            choice = console.input("[bold green]❯[/] ").strip().lower()
        except EOFError:
            console.print("\n[dim](no input; stopping)[/]")
            break
        if choice == "q":
            break
        if choice in ("", "s"):
            continue
        if choice == "o":
            for org in proj.get(kind, oid).obj.get("origin", []):
                console.print(f"  [cyan]{org.get('uri')}[/]")
            continue
        decision = _DECISIONS.get(choice)
        if decision is None:
            console.print("  [dim]? unrecognized; skipped[/]")
            continue
        comment = None
        if decision == "changes_requested":
            try:
                comment = console.input("  [magenta]comment:[/] ").strip() or None
            except EOFError:
                comment = None
        record_decision(proj.root, f"{kind}:{oid}", decision, info["hash"], comment)
        recorded += 1
        console.print(f"  [{_STATUS_STYLE.get(decision, 'white')}]recorded: {decision}[/]")

    if recorded:
        console.print(f"\n[dim]{recorded} decision(s) written to bspec.json.[/]")
    return 0
