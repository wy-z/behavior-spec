"""bspec command-line entry point.

All commands are deterministic: no LLM, no network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import context, loader, review, schema, status
from .model import REVIEW_STATE_FILENAME, Diagnostic, Project


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #
def _collect_diagnostics(root: str) -> tuple[Project, list[Diagnostic]]:
    proj, diags = loader.load_project(root)
    # Semantic and CEL passes are layered in later; import lazily so the base
    # command works before they exist.
    try:
        from . import checks  # noqa: PLC0415
    except ImportError:
        checks = None
    if checks is not None:
        diags = diags + checks.run(proj)
    return proj, diags


def _report(proj: Project, diags: list[Diagnostic], as_json: bool, strict: bool) -> int:
    errors = [d for d in diags if d.severity == "error"]
    warnings = [d for d in diags if d.severity == "warning"]
    counts = {k: len(proj.kind(k)) for k in ("module", "behavior", "invariant", "flow")}

    if as_json:
        out = {
            "ok": not errors and (not warnings or not strict),
            "counts": counts,
            "errors": [d.to_dict() for d in errors],
            "warnings": [d.to_dict() for d in warnings],
        }
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        for d in errors + warnings:
            loc = " ".join(p for p in (d.file, d.path) if p)
            mark = "ERROR" if d.severity == "error" else "warn "
            print(f"{mark} [{d.code}] {d.message}" + (f"  ({loc})" if loc else ""))
        print(
            f"\n{counts['module']} modules, {counts['behavior']} behaviors, "
            f"{counts['invariant']} invariants, {counts['flow']} flows"
        )
        print(f"{len(errors)} errors, {len(warnings)} warnings")

    if errors:
        return 1
    if warnings and strict:
        return 1
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = loader.find_root(args.path or os.getcwd())
    proj, diags = _collect_diagnostics(root)
    return _report(proj, diags, args.json, args.strict)


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
def cmd_init(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.path or os.getcwd())
    os.makedirs(root, exist_ok=True)
    created: list[str] = []

    review_state = os.path.join(root, REVIEW_STATE_FILENAME)
    if not os.path.exists(review_state):
        state = {
            "$schema": "https://bspec.dev/0.1/review-state.schema.json",
            "version": "0.1.0",
            "lang": "en",
            "specGlobs": ["**/*.bspec.json"],
            "reviews": {},
        }
        with open(review_state, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
        created.append(REVIEW_STATE_FILENAME)

    existing = [f for f in os.listdir(root) if f.endswith(".bspec.json")]
    if not existing:
        template = schema.load_embedded("module_template.json")
        example = os.path.join(root, "example.bspec.json")
        with open(example, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
            f.write("\n")
        created.append("example.bspec.json")

    if created:
        print("Initialized bspec project. Created:")
        for c in created:
            print(f"  {c}")
    else:
        print("bspec project already initialized; nothing to do.")
    return 0


# --------------------------------------------------------------------------- #
# status / context / review
# --------------------------------------------------------------------------- #
def cmd_status(args: argparse.Namespace) -> int:
    root = loader.find_root(args.path or os.getcwd())
    proj, _ = loader.load_project(root)
    if args.json:
        print(json.dumps(status.summary(proj), indent=2, sort_keys=True))
    else:
        print(status.render(proj))
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    root = loader.find_root(os.getcwd())
    proj, _ = loader.load_project(root)
    if proj.get("module", args.module) is None:
        print(f"unknown module '{args.module}'", file=sys.stderr)
        return 1
    print(json.dumps(context.export(proj, args.module, args.approved), indent=2, ensure_ascii=False))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    root = loader.find_root(os.getcwd())
    proj, diags = _collect_diagnostics(root)
    if any(d.severity == "error" for d in diags):
        print("Validation errors present; run `bspec validate` before reviewing.", file=sys.stderr)
        return 1
    kinds = {args.kind} if args.kind else None
    status_filter = {args.status} if args.status else None
    return review.run_review(proj, kinds=kinds, module=args.module, status_filter=status_filter)


# --------------------------------------------------------------------------- #
# arg parsing
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bspec", description="Behavior Spec tool (deterministic).")
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("init", help="scaffold a bspec project")
    pi.add_argument("path", nargs="?", help="project directory (default: cwd)")
    pi.set_defaults(func=cmd_init)

    pv = sub.add_parser("validate", help="schema + reference + CEL checks")
    pv.add_argument("path", nargs="?", help="project directory (default: cwd)")
    pv.add_argument("--json", action="store_true", help="machine-readable output")
    pv.add_argument("--strict", action="store_true", help="warnings also fail")
    pv.set_defaults(func=cmd_validate)

    ps = sub.add_parser("status", help="review status per kind and per module")
    ps.add_argument("path", nargs="?", help="project directory (default: cwd)")
    ps.add_argument("--json", action="store_true", help="machine-readable output")
    ps.set_defaults(func=cmd_status)

    pc = sub.add_parser("context", help="export approved behavior for an agent")
    pc.add_argument("--module", required=True, help="module id to export")
    pc.add_argument("--approved", action="store_true", help="only approved+fresh items")
    pc.set_defaults(func=cmd_context)

    pr = sub.add_parser("review", help="interactive review (writes bspec.json)")
    pr.add_argument("--module", help="restrict to one module")
    pr.add_argument("--kind", choices=("module", "behavior", "invariant", "flow"))
    pr.add_argument("--status", help="restrict to one status (default: pending+stale)")
    pr.set_defaults(func=cmd_review)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
