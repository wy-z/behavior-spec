"""Semantic checks over a loaded Project (everything except CEL typing).

CEL parsing/typing/reference-extraction is layered in by the `expression`
module and wired through `_check_cel` once available.
"""

from __future__ import annotations

import os
import re

from .model import CEL_SEGMENT, REVIEW_KINDS, Diagnostic, Project

_ALLOWED_TYPES = {"string", "integer", "number", "boolean", "object", "array"}
_DISALLOWED_SCHEMA_KEYS = (
    "oneOf", "anyOf", "allOf", "not", "if", "then", "else",
    "$ref", "patternProperties", "dependentSchemas", "propertyNames",
)
# Mirrors spec §6 exactly (keep in sync): the only keywords allowed in a
# valueSchema / payloadSchema subset.
_ALLOWED_SCHEMA_KEYS = {
    "type", "properties", "additionalProperties", "items", "enum", "required",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "format",
}
_SEGMENT_RE = re.compile(CEL_SEGMENT)


def run(proj: Project) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    _check_observable_prefix(proj, diags)
    _check_schemas(proj, diags)
    _check_references(proj, diags)
    _check_summaries(proj, diags)
    _check_unused(proj, diags)
    _check_origin_paths(proj, diags)
    _check_flows_and_modules(proj, diags)
    _check_cel(proj, diags)
    return diags


# --------------------------------------------------------------------------- #
# observable prefix-collision (global ban, spec 4.3)
# --------------------------------------------------------------------------- #
def _check_observable_prefix(proj: Project, diags: list[Diagnostic]) -> None:
    ids = sorted((s.id, s) for s in proj.kind("observable").values())
    for i, (a, _) in enumerate(ids):
        for b, sym_b in ids[i + 1:]:
            if b.startswith(a + "."):
                diags.append(
                    Diagnostic(
                        "error", "observable-prefix",
                        f"observable id '{a}' is a prefix of '{b}'; "
                        "the CEL namespace tree would be ambiguous",
                        unit=f"observable:{b}", file=sym_b.file,
                    )
                )


# --------------------------------------------------------------------------- #
# JSON Schema restricted subset (valueSchema / payloadSchema)
# --------------------------------------------------------------------------- #
def _check_schemas(proj: Project, diags: list[Diagnostic]) -> None:
    for sym in proj.kind("observable").values():
        _check_subset(sym.obj.get("valueSchema", {}), f"observable:{sym.id}", "valueSchema",
                      sym.file, diags)
    for sym in proj.kind("event").values():
        ps = sym.obj.get("payloadSchema", {})
        if ps.get("type") != "object":
            diags.append(Diagnostic("error", "schema-subset",
                                    "event payloadSchema must be type 'object'",
                                    unit=f"event:{sym.id}", file=sym.file, path="payloadSchema"))
        _check_subset(ps, f"event:{sym.id}", "payloadSchema", sym.file, diags)


def _check_subset(node: dict, unit: str, path: str, file: str, diags: list[Diagnostic]) -> None:
    if not isinstance(node, dict):
        return

    def err(msg: str, p: str = path) -> None:
        diags.append(Diagnostic("error", "schema-subset", msg, unit=unit, file=file, path=p))

    for key in _DISALLOWED_SCHEMA_KEYS:
        if key in node:
            err(f"'{key}' is not allowed in v0.1 schemas")
    for key in node:
        if key not in _ALLOWED_SCHEMA_KEYS and key not in _DISALLOWED_SCHEMA_KEYS:
            err(f"unknown schema keyword '{key}'")

    t = node.get("type")
    if isinstance(t, list):
        err("union 'type' arrays are not allowed (no null/multi types)")
        return
    if t is None:
        err("schema must declare a 'type' (untyped schemas defeat CEL type-checking)")
        return
    if t not in _ALLOWED_TYPES:
        err(f"type '{t}' is not allowed (no null type in v0.1)")
        return

    if t == "object":
        if node.get("additionalProperties", None) is not False:
            err("object schemas must set additionalProperties:false")
        props = node.get("properties") or {}
        for name, sub in props.items():
            if not _SEGMENT_RE.match(name):
                err(f"property name '{name}' is not a CEL identifier", f"{path}/properties/{name}")
            _check_subset(sub, unit, f"{path}/properties/{name}", file, diags)
        for r in node.get("required", []):
            if r not in props:
                err(f"required property '{r}' is not declared in properties", f"{path}/required")
    elif t == "array":
        items = node.get("items")
        if isinstance(items, list):
            err("tuple 'items' arrays are not allowed")
        elif isinstance(items, dict):
            _check_subset(items, unit, f"{path}/items", file, diags)
        else:
            err("array schema must declare object 'items'")


# --------------------------------------------------------------------------- #
# cross-references + event direction
# --------------------------------------------------------------------------- #
def _check_references(proj: Project, diags: list[Diagnostic]) -> None:
    events = proj.kind("event")
    interfaces = proj.kind("interface")
    behaviors = proj.kind("behavior")

    # event -> interface, with direction compatibility
    for sym in events.values():
        iface_id = sym.obj.get("interface")
        iface = interfaces.get(iface_id)
        if iface is None:
            diags.append(Diagnostic("error", "unresolved-ref",
                                    f"event references unknown interface '{iface_id}'",
                                    unit=f"event:{sym.id}", file=sym.file))
            continue
        ed, idr = sym.obj.get("direction"), iface.obj.get("direction")
        ok = (ed == "input" and idr in ("input", "bidirectional")) or \
             (ed == "output" and idr in ("output", "bidirectional"))
        if not ok:
            diags.append(Diagnostic("error", "direction-mismatch",
                                    f"{ed} event on interface '{iface_id}' with direction '{idr}'",
                                    unit=f"event:{sym.id}", file=sym.file))

    for sym in behaviors.values():
        b = sym.obj
        trig = b.get("when", {}).get("event")
        _require_event(events, trig, "input", sym, "when.event", diags)
        for i, entry in enumerate(b.get("then", [])):
            if "emit" in entry:
                _require_event(events, entry["emit"].get("event"), "output", sym,
                               f"then[{i}].emit.event", diags)
            elif "forbid" in entry:
                _require_event(events, entry["forbid"].get("event"), "output", sym,
                               f"then[{i}].forbid.event", diags)

    for sym in proj.kind("flow").values():
        for i, step in enumerate(sym.obj.get("steps", [])):
            if step not in behaviors:
                diags.append(Diagnostic("error", "unresolved-ref",
                                        f"flow step '{step}' is not a known behavior",
                                        unit=f"flow:{sym.id}", file=sym.file, path=f"steps/{i}"))


def _require_event(events, eid, direction, sym, path, diags) -> None:
    ev = events.get(eid)
    if ev is None:
        diags.append(Diagnostic("error", "unresolved-ref",
                                f"references unknown event '{eid}'",
                                unit=f"behavior:{sym.id}", file=sym.file, path=path))
    elif ev.obj.get("direction") != direction:
        diags.append(Diagnostic("error", "direction-mismatch",
                                f"event '{eid}' must be an {direction} event",
                                unit=f"behavior:{sym.id}", file=sym.file, path=path))


def _check_summaries(proj: Project, diags: list[Diagnostic]) -> None:
    """Every review unit needs a plain-language summary (the reviewer's surface).

    Schema enforces presence + minLength; here we reject the stub pattern where
    summary just echoes the title or id, since that carries no explanation.
    """
    for kind in REVIEW_KINDS:
        for sym in proj.kind(kind).values():
            s = (sym.obj.get("summary") or "").strip()
            title = (sym.obj.get("title") or "").strip()
            if s and (s == title or s == sym.id):
                diags.append(Diagnostic("error", "stub-summary",
                                        f"{kind} '{sym.id}' summary just repeats its title/id; "
                                        "write a plain-language explanation a layperson can review",
                                        unit=f"{kind}:{sym.id}", file=sym.file))


# --------------------------------------------------------------------------- #
# warnings
# --------------------------------------------------------------------------- #
def _check_unused(proj: Project, diags: list[Diagnostic]) -> None:
    used_events: set[str] = set()
    for sym in proj.kind("behavior").values():
        b = sym.obj
        used_events.add(b.get("when", {}).get("event"))
        for entry in b.get("then", []):
            for key in ("emit", "forbid"):
                if key in entry:
                    used_events.add(entry[key].get("event"))
    used_interfaces = {s.obj.get("interface") for s in proj.kind("event").values()}

    for sym in proj.kind("event").values():
        if sym.id not in used_events:
            diags.append(Diagnostic("warning", "unused",
                                    f"event '{sym.id}' is never referenced",
                                    unit=f"event:{sym.id}", file=sym.file))
    for sym in proj.kind("interface").values():
        if sym.id not in used_interfaces:
            diags.append(Diagnostic("warning", "unused",
                                    f"interface '{sym.id}' is never referenced",
                                    unit=f"interface:{sym.id}", file=sym.file))


def _check_origin_paths(proj: Project, diags: list[Diagnostic]) -> None:
    for kind in ("behavior", "invariant"):
        for sym in proj.kind(kind).values():
            for origin in sym.obj.get("origin", []):
                if origin.get("kind") not in ("code", "config", "doc"):
                    continue
                uri = origin.get("uri", "")
                if "://" in uri:
                    continue
                rel = uri.split("#", 1)[0]
                if rel and not os.path.exists(os.path.join(proj.root, rel)):
                    diags.append(Diagnostic("warning", "origin-missing",
                                            f"origin path not found: {rel}",
                                            unit=f"{kind}:{sym.id}", file=sym.file))


def _check_flows_and_modules(proj: Project, diags: list[Diagnostic]) -> None:
    for sym in proj.kind("flow").values():
        if len(sym.obj.get("steps", [])) < 2:
            diags.append(Diagnostic("warning", "thin-flow",
                                    f"flow '{sym.id}' has fewer than 2 steps",
                                    unit=f"flow:{sym.id}", file=sym.file))
    for sym in proj.kind("module").values():
        members = proj.module_members(sym.id)
        if not any(members.values()):
            diags.append(Diagnostic("warning", "empty-module",
                                    f"module '{sym.id}' has no behaviors, invariants, or flows",
                                    unit=f"module:{sym.id}", file=sym.file))


# --------------------------------------------------------------------------- #
# CEL (wired in Slice 3)
# --------------------------------------------------------------------------- #
def _check_cel(proj: Project, diags: list[Diagnostic]) -> None:
    try:
        from . import expression  # noqa: PLC0415
    except ImportError:
        return
    diags.extend(expression.check_project(proj))
