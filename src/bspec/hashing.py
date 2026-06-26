"""Semantic hashing of review units.

The hash covers the human-approved contract: CEL (canonicalized), referenced
observable/event schemas (inlined), and the plain-language `summary` the reviewer
actually approved. Cosmetic edits (formatting, `title`, `origin`, line numbers)
never change it; any operator/operand/schema/summary change does. Module and flow
hashes are membership/order + summary/glossary only (non-cascade) — see spec 13.4.
"""

from __future__ import annotations

import hashlib

import rfc8785

from . import expression
from .model import Project, Symbol


def _cel(node: dict | None) -> str | None:
    if not (isinstance(node, dict) and "cel" in node):
        return None
    try:
        return expression.canonical(node["cel"])
    except Exception:
        # Unparseable CEL is reported by `validate`; hash the raw text so status
        # commands never crash on an in-progress spec.
        return "RAW:" + node["cel"]


def _behavior_payload(proj: Project, sym: Symbol) -> dict:
    b = sym.obj
    events = proj.kind("event")
    observables = proj.kind("observable")

    used_events = set()
    when = b.get("when", {})
    if when.get("event"):
        used_events.add(when["event"])
    then = []
    for entry in b.get("then", []):
        if "assert" in entry:
            then.append({"assert": _cel(entry["assert"])})
        elif "emit" in entry:
            em = entry["emit"]
            used_events.add(em.get("event"))
            then.append({"emit": {"event": em.get("event"), "where": _cel(em.get("where"))}})
        elif "forbid" in entry:
            used_events.add(entry["forbid"].get("event"))
            then.append({"forbid": {"event": entry["forbid"].get("event")}})

    refs = expression.referenced_observables(proj, sym, "behavior")
    return {
        "kind": "behavior",
        "id": sym.id,
        "summary": b.get("summary"),
        "given": _cel(b.get("given")),
        "when": {"event": when.get("event"), "where": _cel(when.get("where"))},
        "then": then,
        "deps": {
            "events": _event_deps(events, used_events),
            "observables": _observable_deps(observables, refs),
        },
    }


def _invariant_payload(proj: Project, sym: Symbol) -> dict:
    inv = sym.obj
    refs = expression.referenced_observables(proj, sym, "invariant")
    return {
        "kind": "invariant",
        "id": sym.id,
        "summary": inv.get("summary"),
        "while": _cel(inv.get("while")),
        "assert": _cel(inv.get("assert")),
        "deps": {"observables": _observable_deps(proj.kind("observable"), refs)},
    }


def _flow_payload(proj: Project, sym: Symbol) -> dict:
    return {"kind": "flow", "id": sym.id, "summary": sym.obj.get("summary"),
            "steps": list(sym.obj.get("steps", []))}


def _module_payload(proj: Project, sym: Symbol) -> dict:
    m = proj.module_members(sym.id)
    return {"kind": "module", "id": sym.id, "summary": sym.obj.get("summary"),
            "glossary": proj.glossary.get(sym.id, {}),
            "members": {"behaviors": m["behavior"], "invariants": m["invariant"], "flows": m["flow"]}}


def _event_deps(events, ids) -> dict:
    out = {}
    for eid in sorted(i for i in ids if i):
        ev = events.get(eid)
        if ev is not None:
            out[eid] = {
                "direction": ev.obj.get("direction"),
                "interface": ev.obj.get("interface"),
                "payloadSchema": ev.obj.get("payloadSchema"),
            }
    return out


def _observable_deps(observables, ids) -> dict:
    out = {}
    for oid in sorted(ids):
        ob = observables.get(oid)
        if ob is not None:
            out[oid] = {"role": ob.obj.get("role"), "valueSchema": ob.obj.get("valueSchema")}
    return out


_PAYLOAD = {
    "behavior": _behavior_payload,
    "invariant": _invariant_payload,
    "flow": _flow_payload,
    "module": _module_payload,
}


def unit_payload(proj: Project, kind: str, oid: str) -> dict | None:
    sym = proj.get(kind, oid)
    builder = _PAYLOAD.get(kind)
    if sym is None or builder is None:
        return None
    return builder(proj, sym)


def hash_payload(payload: dict) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def unit_hash(proj: Project, kind: str, oid: str) -> str | None:
    payload = unit_payload(proj, kind, oid)
    return hash_payload(payload) if payload is not None else None


def all_hashes(proj: Project) -> dict[str, str]:
    """semantic hashes keyed 'kind:id' for every review unit."""
    out: dict[str, str] = {}
    for kind in ("module", "behavior", "invariant", "flow"):
        for oid in proj.kind(kind):
            out[f"{kind}:{oid}"] = unit_hash(proj, kind, oid)  # type: ignore[assignment]
    return out
