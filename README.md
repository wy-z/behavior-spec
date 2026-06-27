# bspec

Deterministic CLI for domain-neutral **Behavior Specs** — describe, review, and consume observable system behavior without prescribing implementation.

- Normative spec: [`docs/spec-v1.md`](docs/spec-v1.md)
- JSON Schema (`$id` `https://wy-z.github.io/behavior-spec/v1/schema.json`): [`src/bspec/schemas/bspec.schema.json`](src/bspec/schemas/bspec.schema.json)

## Concepts

> In some observable context, when an event happens — which observable results the system **must** produce, and which conditions must **always** hold.

A Behavior Spec is authored by a coding agent, checked by the tool, and approved by a human. Fully deterministic — no LLM, no network in core commands.

## Install

Install the `bspec` CLI and the `behavior-spec` agent skill:

```bash
uv tool install bspec --from git+https://github.com/wy-z/behavior-spec && npx skills add https://github.com/wy-z/behavior-spec --skill behavior-spec
```

## Quick start

After installing, you drive bspec by talking to your coding agent (e.g. Claude Code). The `behavior-spec` skill teaches it the workflow and runs the CLI for you:

1. **Initialize** — *"Initialize bspec in the `docs/behavior` folder, with `lang` set to `zh`."*
   → the agent runs `bspec init docs/behavior --lang zh`.
2. **Author** — *"Start writing the behavior specs."*
   → the agent discovers modules, writes `*.bspec.json`, and runs `bspec validate`.
3. **Review** — you approve each rule; the agent never approves its own work:

   ```bash
   bspec review --module <module-id>
   ```

## Commands

```
bspec init        # scaffold a project (--lang <code> sets language)
bspec validate    # schema + reference + CEL type checks
bspec review      # interactive review — the only command that writes review decisions
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
