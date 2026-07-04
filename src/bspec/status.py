"""Review status: pending/stale derivation and per-module rollup.

`pending`/`stale` are computed, never stored:
  - no review record -> pending
  - record hash == current and its decision is still supported -> that decision (fresh)
  - otherwise (hash drifted, or a decision no longer supported such as a legacy
    `deferred`) -> stale (prior decision retained for display)
"""

from __future__ import annotations

import json
import os

from . import hashing
from .model import REVIEW_STATE_FILENAME, Project

REVIEW_KINDS = ("module", "behavior", "invariant", "flow")
STORED_DECISIONS = ("approved", "changes_requested", "rejected")
STATUSES = STORED_DECISIONS + ("stale", "pending")


def load_review_state(root: str) -> dict:
    path = os.path.join(root, REVIEW_STATE_FILENAME)
    if not os.path.exists(path):
        return {"version": "0.1.0", "lang": "en",
                "specGlobs": ["**/*.bspec.json"], "reviews": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute(proj: Project) -> dict[str, dict]:
    """Map 'kind:id' -> {hash, status, prior}."""
    hashes = hashing.all_hashes(proj)
    reviews = load_review_state(proj.root).get("reviews", {})
    out: dict[str, dict] = {}
    for key, h in hashes.items():
        rec = reviews.get(key)
        if rec is None:
            out[key] = {"hash": h, "status": "pending", "prior": None}
        elif rec.get("semanticHash") == h and rec.get("decision") in STORED_DECISIONS:
            out[key] = {"hash": h, "status": rec.get("decision"), "prior": None}
        else:
            out[key] = {"hash": h, "status": "stale", "prior": rec.get("decision")}
    return out


def summary(proj: Project) -> dict:
    units = compute(proj)
    counts = {kind: {s: 0 for s in STATUSES} for kind in REVIEW_KINDS}
    for key, info in units.items():
        kind = key.split(":", 1)[0]
        counts[kind][info["status"]] = counts[kind].get(info["status"], 0) + 1

    modules = {}
    for mid in proj.kind("module"):
        members = proj.module_members(mid)
        rollup = {s: 0 for s in STATUSES}
        for kind, ids in members.items():
            for oid in ids:
                st = units.get(f"{kind}:{oid}", {}).get("status", "pending")
                rollup[st] += 1
        modules[mid] = {
            "scope": units.get(f"module:{mid}", {}).get("status", "pending"),
            "rules": rollup,
        }
    return {"counts": counts, "modules": modules, "units": units}


def render(proj: Project) -> str:
    s = summary(proj)
    lines = []
    for kind in REVIEW_KINDS:
        c = s["counts"][kind]
        active = ", ".join(f"{k}:{v}" for k, v in c.items() if v)
        lines.append(f"{kind+'s':12} {active or 'none'}")
    lines.append("")
    for mid, m in sorted(s["modules"].items()):
        rules = ", ".join(f"{k}:{v}" for k, v in m["rules"].items() if v) or "no rules"
        lines.append(f"module {mid}: scope={m['scope']}; rules: {rules}")
    return "\n".join(lines)
