# bspec

Deterministic CLI for domain-neutral **Behavior Specs** — describe, review, and consume observable system behavior without describing implementation.

See [`docs/spec-v1.md`](docs/spec-v1.md) for the normative specification.

## Concepts

> In some observable context, when an event happens, which observable results the system **must** produce; and which conditions must **always** hold.

A Behavior Spec is written by a Code Agent; review state is written only by this tool; a human approves. The tool is fully deterministic — no LLM, no network in core commands.

## Commands

```
bspec init        # scaffold a project
bspec validate    # schema + reference + CEL type checks
bspec review      # interactive review (only writer of bspec.json)
bspec status      # per-kind / per-module review status
bspec context     # export approved behavior for an agent
```

## Develop

```
uv sync --extra dev
uv run pytest
uv run bspec --help
```
