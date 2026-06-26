# bspec

Deterministic CLI for domain-neutral **Behavior Specs** — describe, review, and consume observable system behavior without describing implementation.

- Repository: <https://github.com/wy-z/behavior-spec>
- Normative spec: [`docs/spec-v1.md`](docs/spec-v1.md)
- JSON Schema (`$id` `https://wy-z.github.io/behavior-spec/v1/schema.json`): [`src/bspec/schemas/bspec.schema.json`](src/bspec/schemas/bspec.schema.json)

## Concepts

> In some observable context, when an event happens, which observable results the system **must** produce; and which conditions must **always** hold.

A Behavior Spec is written by a Code Agent; review state is written only by this tool; a human approves. The tool is fully deterministic — no LLM, no network in core commands.

## Commands

```
bspec init        # scaffold a project (--lang <code> sets language)
bspec validate    # schema + reference + CEL type checks
bspec review      # interactive review (only writer of bspec.json)
bspec status      # per-kind / per-module review status
bspec doc         # markdown + mermaid (flow / module diagrams) for GitHub/sharing
```

## Develop

```
git clone https://github.com/wy-z/behavior-spec
cd behavior-spec
uv sync --extra dev
uv run pytest
uv run bspec --help
```
