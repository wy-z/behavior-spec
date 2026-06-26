"""Core data model: the loaded project, its symbol tables, and diagnostics.

Objects are kept as validated dicts (their shape is guaranteed by the meta-schema);
this module adds the cross-object indexing that later passes need.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Review-unit kinds and the supporting (non-reviewed) definition kinds.
REVIEW_KINDS = ("module", "behavior", "invariant", "flow")
DEFINITION_KINDS = ("interface", "observable", "event")
ALL_KINDS = REVIEW_KINDS + DEFINITION_KINDS

# Ids that are addressed inside CEL (so they must be dot-separated CEL identifiers).
CEL_ADDRESSABLE_KINDS = ("observable",)  # parameters are observables with role=parameter

GENERAL_ID = r"^[a-z][a-z0-9_]*(?:[.-][a-z0-9_]+)*$"
CEL_ID = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$"
CEL_SEGMENT = r"^[a-z][a-z0-9_]*$"  # event payload / object property names

# Review-state container at the project root (visible file, not a dotfile).
# Distinct from spec files, which match the project's specGlobs (default **/*.bspec.json).
REVIEW_STATE_FILENAME = "bspec.json"


@dataclass(frozen=True)
class Diagnostic:
    severity: str  # "error" | "warning"
    code: str
    message: str
    unit: str | None = None  # e.g. "behavior:orders.create"
    file: str | None = None
    path: str | None = None  # JSON pointer-ish location within the file

    def to_dict(self) -> dict:
        d = {"severity": self.severity, "code": self.code, "message": self.message}
        for k in ("unit", "file", "path"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d


@dataclass
class SpecFile:
    path: str  # relative to project root
    raw: dict


@dataclass
class Symbol:
    kind: str
    id: str
    obj: dict
    file: str  # source file path


@dataclass
class Project:
    root: str
    files: list[SpecFile] = field(default_factory=list)
    # kind -> id -> Symbol  (first declaration wins; duplicates are reported separately)
    symbols: dict[str, dict[str, Symbol]] = field(default_factory=dict)
    # (kind, id) -> module id  for review-unit members (behavior/invariant/flow),
    # derived from the module declared in the same file.
    membership: dict[tuple[str, str], str] = field(default_factory=dict)
    # module id -> { term: plain-language definition }  (file-level glossary)
    glossary: dict[str, dict[str, str]] = field(default_factory=dict)

    def kind(self, kind: str) -> dict[str, Symbol]:
        return self.symbols.get(kind, {})

    def get(self, kind: str, id: str) -> Symbol | None:
        return self.symbols.get(kind, {}).get(id)

    def module_members(self, module_id: str) -> dict[str, list[str]]:
        """Sorted member ids of a module, grouped by kind."""
        out: dict[str, list[str]] = {"behavior": [], "invariant": [], "flow": []}
        for (kind, oid), mid in self.membership.items():
            if mid == module_id and kind in out:
                out[kind].append(oid)
        for kind in out:
            out[kind].sort()
        return out

    def behaviors(self) -> list[Symbol]:
        return list(self.kind("behavior").values())

    def invariants(self) -> list[Symbol]:
        return list(self.kind("invariant").values())

    def modules(self) -> list[Symbol]:
        return list(self.kind("module").values())
