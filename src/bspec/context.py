"""Approved-context export for a Code Agent.

The per-item gate is authoritative: with approved=True only individually
approved-and-fresh behaviors/invariants are exported. Module staleness never
blocks an approved-fresh behavior, and a fresh-approved module never exports a
stale one (spec 13.4 / 16).
"""

from __future__ import annotations

from . import expression, status
from .model import Project


def export(proj: Project, module_id: str, approved: bool = False) -> dict:
    units = status.compute(proj)
    members = proj.module_members(module_id)

    def status_of(kind: str, oid: str) -> str:
        return units.get(f"{kind}:{oid}", {}).get("status", "pending")

    def keep(kind: str, oid: str) -> bool:
        return not approved or status_of(kind, oid) == "approved"

    def annotate(kind: str, oid: str) -> dict:
        obj = proj.get(kind, oid).obj
        return obj if approved else {**obj, "reviewStatus": status_of(kind, oid)}

    kept_behaviors = [i for i in members["behavior"] if keep("behavior", i)]
    kept_invariants = [i for i in members["invariant"] if keep("invariant", i)]

    obs_ids: set[str] = set()
    event_ids: set[str] = set()
    for bid in kept_behaviors:
        sym = proj.get("behavior", bid)
        obs_ids |= expression.referenced_observables(proj, sym, "behavior")
        b = sym.obj
        if b.get("when", {}).get("event"):
            event_ids.add(b["when"]["event"])
        for entry in b.get("then", []):
            for k in ("emit", "forbid"):
                if k in entry:
                    event_ids.add(entry[k].get("event"))
    for iid in kept_invariants:
        obs_ids |= expression.referenced_observables(proj, proj.get("invariant", iid), "invariant")

    iface_ids: set[str] = set()
    events = []
    for eid in sorted(e for e in event_ids if e):
        ev = proj.get("event", eid)
        if ev:
            events.append(ev.obj)
            if ev.obj.get("interface"):
                iface_ids.add(ev.obj["interface"])

    kept_set = set(kept_behaviors)
    flows = []
    for fid in members["flow"]:
        steps = proj.get("flow", fid).obj.get("steps", [])
        # With --approved a flow ships only if it is itself approved+fresh AND every
        # step is too; a partial flow would misrepresent the sequence, so omit it.
        if approved and not (keep("flow", fid) and all(s in kept_set for s in steps)):
            continue
        flows.append(annotate("flow", fid))

    mod = proj.get("module", module_id)
    return {
        "module": mod.obj if mod else {"id": module_id},
        "lang": status.load_review_state(proj.root).get("lang", "en"),
        "glossary": proj.glossary.get(module_id, {}),
        "behaviors": [annotate("behavior", i) for i in kept_behaviors],
        "invariants": [annotate("invariant", i) for i in kept_invariants],
        "dependencies": {
            "interfaces": [proj.get("interface", i).obj for i in sorted(iface_ids) if proj.get("interface", i)],
            "events": events,
            "observables": [proj.get("observable", o).obj for o in sorted(obs_ids) if proj.get("observable", o)],
        },
        "flows": flows,
    }
