"""Interactive review — the ONLY writer of the review-state file (bspec.json).

The Agent never writes review records; only this module does, and only from an
explicit human decision. Rendering uses `rich`; the verdict/loop logic stays
plain stdlib so piped input keeps working.
"""

from __future__ import annotations

import datetime as _dt
import json
import os

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import expression, status
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


def _rule_grid() -> Table:
    g = Table.grid(padding=(0, 2))
    g.add_column(style="bold cyan", justify="right", no_wrap=True)
    g.add_column(overflow="fold")
    return g


def _refs_panel(proj: Project, sym, kind: str):
    """Sub-panel listing referenced observables/events with their human titles."""
    t = Table.grid(padding=(0, 1))
    t.add_column(style="dim", no_wrap=True)
    t.add_column(style="magenta", no_wrap=True)
    t.add_column(overflow="fold", style="dim")
    rows = 0
    for oid in sorted(expression.referenced_observables(proj, sym, kind)):
        s = proj.get("observable", oid)
        if s:
            t.add_row("obs", oid, s.obj.get("title") or s.obj.get("description") or "")
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
                t.add_row("evt", eid, s.obj.get("title") or "")
                rows += 1
    if not rows:
        return None
    return Panel(t, title="referenced", title_align="left", border_style="dim",
                 box=box.MINIMAL, padding=(0, 1))


def _glossary_panel(proj: Project, kind: str, oid: str):
    mid = oid if kind == "module" else proj.membership.get((kind, oid))
    gloss = proj.glossary.get(mid, {})
    if not gloss:
        return None
    t = Table.grid(padding=(0, 1))
    t.add_column(style="bold", justify="right", no_wrap=True)
    t.add_column(overflow="fold", style="dim")
    for term, defn in gloss.items():
        t.add_row(term, defn)
    return Panel(t, title="glossary", title_align="left", border_style="dim",
                 box=box.MINIMAL, padding=(0, 1))


def _members_table(proj: Project, oid: str, units: dict):
    members = proj.module_members(oid)
    t = Table(box=box.SIMPLE, show_header=True, header_style="dim", expand=True)
    t.add_column("kind", style="dim", no_wrap=True)
    t.add_column("status", no_wrap=True)
    t.add_column("id", style="cyan", no_wrap=True)
    t.add_column("title", style="dim", overflow="fold")
    any_row = False
    for mk in ("behavior", "invariant", "flow"):
        for mid in members[mk]:
            any_row = True
            st = units.get(f"{mk}:{mid}", {}).get("status", "pending")
            t.add_row(mk, _badge(st), mid, proj.get(mk, mid).obj.get("title") or "")
    return t if any_row else None


def _card(proj: Project, kind: str, oid: str, info: dict, units: dict | None = None) -> Panel:
    """A self-contained, styled approval card: title, summary, the rule, and every
    term it relies on (referenced observables/events + glossary)."""
    o = proj.get(kind, oid).obj
    if units is None:
        units = status.compute(proj)
    body: list = []
    if o.get("title"):
        body.append(Text(o["title"], style="bold"))
    if o.get("summary"):
        body.append(Text(o["summary"]))
    body.append(Text(""))

    rule = _rule_grid()
    if kind == "behavior":
        if "given" in o:
            rule.add_row("GIVEN", Text(_cel(o["given"]), style="green"))
        w = o.get("when", {})
        rule.add_row("WHEN", _event_text("", w.get("event"), w.get("where")))
        for entry in o.get("then", []):
            if "assert" in entry:
                rule.add_row("MUST", Text.assemble(("assert ", "dim"), (_cel(entry["assert"]), "green")))
            elif "emit" in entry:
                rule.add_row("MUST", _event_text("emit ", entry["emit"].get("event"), entry["emit"].get("where")))
            elif "forbid" in entry:
                rule.add_row("MUST", _event_text("forbid ", entry["forbid"].get("event"), None))
        body += [rule, _refs_panel(proj, proj.get(kind, oid), kind)]
    elif kind == "invariant":
        if "while" in o:
            rule.add_row("WHILE", Text(_cel(o["while"]), style="green"))
        rule.add_row("ASSERT", Text(_cel(o.get("assert")), style="green"))
        body += [rule, _refs_panel(proj, proj.get(kind, oid), kind)]
    elif kind == "flow":
        for step in o.get("steps", []):
            st = proj.get("behavior", step)
            label = (st.obj.get("title") or "") if st else "(unknown)"
            rule.add_row("STEP", Text.assemble((step, "yellow"), (f"  {label}", "dim")))
        body.append(rule)
    elif kind == "module":
        body.append(_members_table(proj, oid, units))

    body.append(_glossary_panel(proj, kind, oid))

    origins = o.get("origin", [])
    if origins:
        locs = []
        for org in origins:
            loc = org.get("uri", "")
            if org.get("lineStart"):
                loc += f":{org['lineStart']}-{org.get('lineEnd', org['lineStart'])}"
            locs.append(loc)
        body.append(Text("origin  " + "   ".join(locs), style="dim"))

    head = Text.assemble((f"{kind.upper()} ", "bold"), (oid, "bold white"))
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
    console = Console()
    if not items:
        console.print("[dim]Nothing to review for that filter.[/]")
        return 0

    recorded = 0
    for n, (kind, oid, info) in enumerate(items, 1):
        console.print()
        console.rule(f"[dim]{n}/{len(items)}[/]", align="left")
        console.print(_card(proj, kind, oid, info, units))
        console.print(
            "[green]a[/]pprove  [magenta]c[/]hanges  [red]r[/]eject  "
            "[blue]d[/]efer  [cyan]o[/]rigin  [dim]s[/]kip  [dim]q[/]uit"
        )
        try:
            choice = input("> ").strip().lower()
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
                comment = input("  comment: ").strip() or None
            except EOFError:
                comment = None
        record_decision(proj.root, f"{kind}:{oid}", decision, info["hash"], comment)
        recorded += 1
        console.print(f"  [{_STATUS_STYLE.get(decision, 'white')}]recorded: {decision}[/]")

    if recorded:
        console.print(f"\n[dim]{recorded} decision(s) written to bspec.json.[/]")
    return 0
