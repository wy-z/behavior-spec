"""Interactive review — writes the review-state file (bspec.json) from human decisions.

Every record this module writes comes from an explicit human keypress. Rendering
uses `rich`; the verdict/loop logic stays plain stdlib so piped input keeps working.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys

import termaid
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.segment import Segment
from rich.table import Table
from rich.text import Text

from . import diagram, expression, status
from .model import REVIEW_STATE_FILENAME, Project

_DECISIONS = {"a": "approved", "c": "changes_requested", "r": "rejected"}


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
    "rejected": "red", "stale": "red",
}


def _cel(node) -> str:
    return node.get("cel", "") if isinstance(node, dict) else ""


def _badge(stat: str) -> Text:
    return Text(f" {stat} ", style=f"reverse {_STATUS_STYLE.get(stat, 'white')}")


def _typed_name(kind: str, obj: dict, oid: str, labels: dict) -> str:
    """`[kind][direction] readable-name`. The tag is the object's raw kind +
    direction/role, prepended at display time so a reviewer always sees *what a
    unit is*. `labels` (the type-word `glossary` in bspec.json) localizes each
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
    """The module's boundary: one row per event crossing it (inputs first, then
    outputs), with the event's id and the `from`/`to` interface it crosses. The
    interface shows only as that dim channel — a reviewer judges the events, so the
    title names just them. The precise typed contract (payload schemas) is the
    agent's view via `bspec doc` (diagram.module_mermaid), not this card."""
    edges = diagram.module_io(proj, proj.get("module", oid))
    if not edges:
        return None
    t = _section(header=True, lines=True)
    t.add_column("name", overflow="fold")
    t.add_column("id", style="dim", no_wrap=True)
    t.add_column("interface", style="dim", no_wrap=True)
    for d in ("input", "output"):
        prep = labels.get("from", "from") if d == "input" else labels.get("to", "to")
        for e in (x for x in edges if x.direction == d):
            ev, iface = proj.get("event", e.event), proj.get("interface", e.interface)
            ename = (ev.obj.get("name") or e.event) if ev else e.event
            iname = (iface.obj.get("name") or e.interface) if iface else e.interface
            t.add_row(Text(ename), e.event, f"{prep} {iname}")
    return _titled(labels.get("event", "event"), t)


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
# Decisions are letters, never arrows: on the alt-screen the mouse wheel is delivered
# AS ↑/↓ (xterm "alternate scroll"). Binding ↑/↓ to scrolling the card means the wheel
# scrolls (as users expect) and can never reach a decision.
_KEYCAPS = [
    ("← →", "unit", "cyan"), ("↑ ↓", "scroll", "cyan"), ("a", "approve", "green"),
    ("r", "reject", "red"), ("c", "changes", "magenta"), ("q", "quit", "white"),
]
# `view` is the same carousel, read-only — navigation/scroll only, no decision keys.
_VIEW_KEYCAPS = [
    ("← →", "unit", "cyan"), ("↑ ↓", "scroll", "cyan"), ("q", "quit", "white"),
]


def _footer(idx: int, total: int, keycaps: list) -> Panel:
    """Keycap toolbar + position."""
    bar = Text()
    bar.append(f" {idx + 1}/{total} ", style="reverse")
    for cap, label, color in keycaps:
        bar.append("   ")
        bar.append(f" {cap} ", style=f"reverse {color}")
        bar.append(f" {label}", style=color)
    return Panel(bar, box=box.ROUNDED, border_style="dim", padding=(0, 1))


def _read_key(fd: int) -> str:
    """One logical keypress from a cbreak terminal: 'up'/'down'/'left'/'right', 'enter',
    'eof', 'esc' (a lone Escape), or a lowercased character ('' for anything to ignore).
    A lone Esc is told apart from an escape *sequence* by whether bytes follow within a
    short deadline; a CSI/SS3 sequence is consumed through its final byte so leftover bytes
    can never read back as a keystroke (only the four arrows map; everything else ignored)."""
    import select

    b = os.read(fd, 1)
    if not b:
        return "eof"
    if b == b"\x03":
        raise KeyboardInterrupt
    if b in (b"\r", b"\n"):
        return "enter"
    if b == b"\x1b":
        if not select.select([fd], [], [], 0.05)[0]:
            return "esc"  # nothing follows → a real, lone Escape
        intro = os.read(fd, 1)
        if intro not in (b"[", b"O"):
            return ""  # ESC + non-CSI (e.g. an Alt-combo) — ignore, never quit
        seq = intro
        while select.select([fd], [], [], 0.05)[0]:
            c = os.read(fd, 1)
            if not c:
                break
            seq += c
            if 0x40 <= c[0] <= 0x7E:  # a CSI/SS3 final byte ends the sequence
                break
        return {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left",
                b"OA": "up", b"OB": "down", b"OC": "right", b"OD": "left"}.get(seq, "")
    return b.decode("utf-8", "ignore").lower()


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


def _tty_ok() -> bool:
    """The fullscreen carousel needs a real terminal it can switch to raw input.
    Piped/redirected stdin (CI, `echo … | bspec review`) or a platform without
    `termios` (Windows) drops to the line-based reader instead."""
    import importlib.util

    if importlib.util.find_spec("termios") is None:
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask_comment(live, console: Console, fd: int, saved) -> str | None:
    """Leave the alt-screen and read a changes-comment in cooked mode, so native
    line editing and multibyte (e.g. Chinese) input work; then re-enter raw mode and
    the alt-screen. Empty input cancels. `live` is reused, so reset the overflow that
    `Live.stop()` flips to 'visible' before resuming."""
    import termios
    import tty

    live.stop()
    termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    try:
        comment = console.input("[magenta]comment (empty to cancel):[/] ").strip() or None
    except (EOFError, KeyboardInterrupt):
        comment = None
    tty.setcbreak(fd)
    live.vertical_overflow = "crop"
    live.start(refresh=True)
    return comment


class _SegLines:
    """Wrap already-rendered segment lines as a renderable, so the carousel can paint a
    scrolled window of a card that is taller than the screen."""

    def __init__(self, lines: list):
        self._lines = lines

    def __rich_console__(self, console: Console, options):
        for line in self._lines:
            yield from line
            yield Segment.line()


def _frame(console: Console, card, foot, scroll: int):
    """One scrolled frame: render `card` to full-width lines (pad=True → a scroll repaint
    leaves no stale cells) and window it to top offset `scroll` (clamped to the card
    height), with `foot` pinned below a scroll indicator. Returns the renderable and the
    maximum scroll offset, so the caller can clamp its own state to match."""
    full = console.options.update(height=None)
    lines = console.render_lines(card, full)
    view_h = max(1, console.size.height - len(console.render_lines(foot, full)) - 1)
    max_scroll = max(0, len(lines) - view_h)
    scroll = min(scroll, max_scroll)
    bar = (f"  ↕ {scroll + 1}–{min(scroll + view_h, len(lines))}/{len(lines)}   ↑/↓ scroll"
           if max_scroll else "")
    window = Group(_SegLines(lines[scroll:scroll + view_h]), Text(bar, style="dim"), foot)
    return window, max_scroll


def _run_carousel(proj: Project, console: Console, items: list, units: dict,
                  read_only: bool = False) -> int:
    """Fullscreen one-card-at-a-time browser: ←/→ page between units; ↑/↓ (and the mouse
    wheel) scroll a card taller than the screen; `q` quit. Unless `read_only`, it also
    reviews — `a` approve, `r` reject, `c` request changes — recording each decision and
    advancing. Decisions are letter keys, never arrows (see _KEYCAPS); a decision repaints
    the card in place (its status is the same dict `units` holds). Past the last card ends."""
    import termios
    import tty
    from rich.live import Live

    keycaps = _VIEW_KEYCAPS if read_only else _KEYCAPS
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    recorded = 0
    idx = 0
    scroll = 0

    def decide(decision: str, comment: str | None = None) -> None:
        nonlocal recorded, idx
        kind, oid, info = items[idx]
        record_decision(proj.root, f"{kind}:{oid}", decision, info["hash"], comment)
        info["status"] = decision
        info.pop("prior", None)
        recorded += 1
        idx += 1  # advance; loop exits when this passes the last card

    try:
        tty.setcbreak(fd)
        with Live(console=console, screen=True, auto_refresh=False,
                  vertical_overflow="crop") as live:
            while idx < len(items):
                kind, oid, info = items[idx]
                card = _card(proj, kind, oid, info, units)
                window, max_scroll = _frame(
                    console, card, _footer(idx, len(items), keycaps), scroll)
                scroll = min(scroll, max_scroll)
                live.update(window)
                live.refresh()
                key = _read_key(fd)
                if key in ("q", "esc", "eof"):
                    break
                if key == "up":
                    scroll = max(0, scroll - 1)
                elif key == "down":
                    scroll = min(max_scroll, scroll + 1)
                elif key == "left":
                    idx, scroll = max(0, idx - 1), 0
                elif key == "right":
                    idx, scroll = min(len(items) - 1, idx + 1), 0
                elif not read_only and key == "a":
                    decide("approved")
                    scroll = 0
                elif not read_only and key == "r":
                    decide("rejected")
                    scroll = 0
                elif not read_only and key == "c":
                    comment = _ask_comment(live, console, fd, saved)
                    if comment:
                        decide("changes_requested", comment)
                    scroll = 0
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    if not read_only:
        msg = (f"{recorded} decision(s) written to {REVIEW_STATE_FILENAME}."
               if recorded else "No decisions recorded.")
        console.print(f"\n[dim]{msg}[/]")
    return 0


def _run_linear(proj: Project, console: Console, items: list, units: dict) -> int:
    """Line-based fallback for non-terminal stdin (pipes/CI): print each card and read
    a single letter — a approve, r reject, c changes, s/⏎ skip, q quit."""
    recorded = 0
    for n, (kind, oid, info) in enumerate(items, 1):
        console.print()
        console.rule(f"[dim]{n}/{len(items)}[/]", align="left")
        console.print(_card(proj, kind, oid, info, units))
        console.print("[dim]a approve  r reject  c changes  s skip  q quit[/]")
        try:
            choice = console.input("[bold green]❯[/] ").strip().lower()
        except EOFError:
            break
        if choice == "q":
            break
        if choice in ("", "s"):
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
            if comment is None:
                console.print("  [dim]changes need a comment; skipped[/]")
                continue
        record_decision(proj.root, f"{kind}:{oid}", decision, info["hash"], comment)
        recorded += 1
        console.print(f"  [{_STATUS_STYLE.get(decision, 'white')}]recorded: {decision}[/]")

    if recorded:
        console.print(f"\n[dim]{recorded} decision(s) written to {REVIEW_STATE_FILENAME}.[/]")
    return 0


def _make_console() -> Console:
    # Cap at a readable column: a review card reads like prose, and on a very wide
    # terminal an unbounded card sprawls (columns spread, diagrams float in space).
    console = Console()
    return Console(width=100) if console.size.width > 100 else console


def run_review(proj: Project, kinds=None, module=None, status_filter=None) -> int:
    units = status.compute(proj)
    if status_filter is None:
        status_filter = {"pending", "stale"}
    items = _select(proj, units, kinds, module, status_filter)
    console = _make_console()
    if not items:
        console.print("[dim]Nothing to review for that filter.[/]")
        return 0
    if _tty_ok():
        return _run_carousel(proj, console, items, units)
    return _run_linear(proj, console, items, units)


def run_view(proj: Project, kinds=None, module=None, status_filter=None) -> int:
    """Read-only browse of the same cards — every unit by default, regardless of status,
    so approved work stays viewable. Writes nothing. Non-terminal stdin prints the cards."""
    units = status.compute(proj)
    items = _select(proj, units, kinds, module, status_filter)
    console = _make_console()
    if not items:
        console.print("[dim]No units to view.[/]")
        return 0
    if _tty_ok():
        return _run_carousel(proj, console, items, units, read_only=True)
    for n, (kind, oid, info) in enumerate(items, 1):
        console.rule(f"[dim]{n}/{len(items)}[/]", align="left")
        console.print(_card(proj, kind, oid, info, units))
    return 0
