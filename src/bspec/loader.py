"""Discover, parse, schema-validate, and index spec files into a Project."""

from __future__ import annotations

import glob
import json
import os

from . import schema as schema_mod
from .model import ALL_KINDS, REVIEW_STATE_FILENAME, Diagnostic, Project, SpecFile, Symbol

# kind -> the document array that holds objects of that kind
KIND_TO_ARRAY = {
    "interface": "interfaces",
    "observable": "observables",
    "event": "events",
    "behavior": "behaviors",
    "invariant": "invariants",
    "flow": "flows",
}


_IGNORE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", ".omc",
}


def find_root(start: str) -> str:
    """Project root = the directory holding the review-state file (bspec.json).

    Resolution order:
      1. nearest ancestor of `start` with bspec.json   (run from inside the project),
      2. else shallowest descendant with bspec.json     (run from above it, e.g. repo root),
      3. else nearest ancestor with a bare behavior/ dir (legacy, no review-state file),
      4. else `start`.
    """
    start = os.path.abspath(start)

    def _walk_up(test) -> str | None:
        cur = start
        while True:
            if test(cur):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                return None
            cur = parent

    return (
        _walk_up(lambda d: os.path.exists(os.path.join(d, REVIEW_STATE_FILENAME)))
        or _find_down(start)
        or _walk_up(lambda d: os.path.isdir(os.path.join(d, "behavior")))
        or start
    )


def _find_down(start: str) -> str | None:
    """Shallowest directory under `start` that contains a review-state file."""
    best: str | None = None
    best_depth: int | None = None
    for dirpath, dirnames, filenames in os.walk(start):
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORE_DIRS and not d.startswith("."))
        if REVIEW_STATE_FILENAME in filenames:
            depth = os.path.relpath(dirpath, start).count(os.sep)
            if best_depth is None or depth < best_depth:
                best, best_depth = dirpath, depth
    return best


# Specs are found anywhere under the root by default; a `behavior/` subdir is just
# one convention. Override per project via `specGlobs` in bspec.json.
DEFAULT_SPEC_GLOBS = ["**/*.bspec.json"]


def spec_globs(root: str) -> tuple[list[str], list[Diagnostic]]:
    """Spec-file globs from the project's review-state file, or the default.

    An unreadable review-state file is an error diagnostic, never a silent
    fallback — it would quietly change which spec files load.
    """
    path = os.path.join(root, REVIEW_STATE_FILENAME)
    if not os.path.exists(path):
        return DEFAULT_SPEC_GLOBS, []
    try:
        with open(path, encoding="utf-8") as f:
            globs = json.load(f).get("specGlobs")
    except (OSError, json.JSONDecodeError) as e:
        return DEFAULT_SPEC_GLOBS, [Diagnostic(
            "error", "review-state-read",
            f"cannot read {REVIEW_STATE_FILENAME} ({e}); using default specGlobs",
            file=REVIEW_STATE_FILENAME)]
    if isinstance(globs, list) and globs and all(isinstance(g, str) for g in globs):
        return globs, []
    return DEFAULT_SPEC_GLOBS, []


def load_project(root: str) -> tuple[Project, list[Diagnostic]]:
    """Load every spec file matched by the project's specGlobs into an indexed Project."""
    proj = Project(root=root, symbols={k: {} for k in ALL_KINDS})
    root_real = os.path.realpath(root)
    seen: set[str] = set()

    globs, diags = spec_globs(root)
    for g in globs:
        for abspath in sorted(glob.glob(os.path.join(root, g), recursive=True)):
            real = os.path.realpath(abspath)
            # Reject matches (absolute globs, ../ escapes) that leave the root.
            if real != root_real and not real.startswith(root_real + os.sep):
                diags.append(Diagnostic(
                    "warning", "spec-glob-escape",
                    f"ignored spec file outside project root: {os.path.relpath(abspath, root)}",
                    file=g))
                continue
            if real in seen:
                continue
            seen.add(real)

            rel = os.path.relpath(abspath, root)
            try:
                with open(abspath, encoding="utf-8") as f:
                    raw = json.load(f)
            except json.JSONDecodeError as e:
                diags.append(Diagnostic("error", "json", f"invalid JSON: {e}", file=rel))
                continue

            sf = SpecFile(path=rel, raw=raw)
            proj.files.append(sf)

            file_diags = schema_mod.validate_file(raw, rel)
            diags.extend(file_diags)
            if any(d.severity == "error" for d in file_diags):
                # A structurally invalid file is not indexed; downstream passes
                # would only produce noise on top of the schema errors.
                continue

            _index_file(proj, sf, diags)

    return proj, diags


def _index_file(proj: Project, sf: SpecFile, diags: list[Diagnostic]) -> None:
    mod = sf.raw.get("module")
    mod_id = mod.get("id") if isinstance(mod, dict) else None
    if isinstance(mod, dict):
        _add(proj, "module", mod, sf, diags)
        gloss = sf.raw.get("glossary")
        if isinstance(gloss, dict) and mod_id:
            proj.glossary[mod_id] = gloss
    for kind, array in KIND_TO_ARRAY.items():
        for obj in sf.raw.get(array, []):
            _add(proj, kind, obj, sf, diags)
            oid = obj.get("id")
            if mod_id and isinstance(oid, str) and kind in ("behavior", "invariant", "flow"):
                proj.membership[(kind, oid)] = mod_id


def _add(
    proj: Project, kind: str, obj: dict, sf: SpecFile, diags: list[Diagnostic]
) -> None:
    oid = obj.get("id")
    if not isinstance(oid, str):
        return
    table = proj.symbols[kind]
    existing = table.get(oid)
    if existing is not None:
        diags.append(
            Diagnostic(
                "error",
                "duplicate-id",
                f"duplicate {kind} id '{oid}' (already declared in {existing.file})",
                unit=f"{kind}:{oid}",
                file=sf.path,
            )
        )
        return
    table[oid] = Symbol(kind=kind, id=oid, obj=obj, file=sf.path)
