# Behavior Spec cheat sheet (v1)

The working reference for authoring, validating, and reviewing Behavior Specs
with the `bspec` CLI.

## Object types (one module per file)

| Object | Purpose |
|---|---|
| `module` | Human review boundary (NOT a code package). |
| `interface` | Observable boundary; `direction` input/output/bidirectional. |
| `observable` | A reviewable value; `role` state/parameter; restricted `valueSchema`. |
| `event` | Input or output at a point in time; `direction`; `interface` ref; `payloadSchema`. |
| `behavior` | `given` + `when` → `then`; optional `actor` (who initiates). One trigger event, one business reaction. |
| `invariant` | `while` → `assert`; must always hold. |
| `flow` | Ordered behavior ids; navigation only, non-normative. |
| `origin` | Why the agent derived a spec (file-level); review metadata, non-normative. |

Every object has a `name` (short label, **cosmetic**; the tool prepends the raw
`[kind][direction]` tag at review — never author it). `name` and `origin.note` are
non-normative. Review units (module/behavior/invariant/flow) need a `rationale`
(why) and — for behavior/invariant — a `title` (EARS requirement): **both are in
the semantic hash** (the reviewer approves from them). A definition's optional
`description` is hashed *when referenced* by a rule. An optional file-level
`glossary` (`{ "term": "definition" }`) is also hashed into the module.

## CEL namespaces and per-clause allow-list

| Namespace | Contents |
|---|---|
| `before` / `after` / `current` | observables with role `state` |
| `params` | observables with role `parameter` |
| `trigger` | the input event payload |
| `emitted` | the expected output event payload |

| Clause | Allowed namespaces |
|---|---|
| `given` | before, params |
| `when.where` | before, params, trigger |
| `then.assert` | before, after, params, trigger |
| `then.emit.where` | before, after, params, trigger, emitted |
| `invariant.while` / `invariant.assert` | current, params |

Path resolution: `before.portfolio.gross_exposure` resolves the longest declared
observable id, then field-accesses into its `valueSchema`. Every expression must
parse, type-check, and return `bool`.

## then semantics

- Multiple `then` entries = conjunction (all MUST hold).
- `assert`: after the behavior, the asserted condition over observables holds.
- `emit`: the system MUST produce ≥1 output event of that type for which `where` holds.
- `forbid`: the system MUST NOT produce any output event of that type (no `where` in v0.1).
- No `SHOULD`/`MAY`. Uncertainty goes in a review comment, never an approved spec.

## Conflicts & precedence

No implicit priority. If two behaviors could both fire under the same
conditions, make their conditions mutually exclusive. (Declarative `overrides`
is deferred to v0.2.)

## Allowed JSON Schema subset (valueSchema / payloadSchema)

Allowed: `string | integer | number | boolean | object | array`, `enum`, and
common annotations (`minimum`, `maximum`, `pattern`, `minLength`, `required`, …).
Every schema node must declare a `type`; objects must set
`additionalProperties: false`; arrays use a single `items` schema. Unknown keywords
and `required` entries not declared in `properties` are rejected.

Disallowed in v0.1: `oneOf`, `anyOf`, `allOf`, `not`, `if/then/else`, `$ref`,
`patternProperties`, tuple `items`, `type` arrays, `type: "null"`. No null type —
an optional field is simply absent from `required` and guarded with CEL `has()`.

Type mapping for CEL: string→string, integer→int, number→double, boolean→bool,
object→typed object, array→list.

## Review status (computed, never stored)

- no review record → `pending`
- record hash == current → the recorded decision (`approved` / `rejected` / `disputed`)
- record hash != current → `stale`
- `disputed` = a reviewer's flagged reservation, reason in `comment` (the human's `[c]` key,
  or a delegated agent instead of approving); `bspec review` shows it by default so the human
  resolves it. It is the sole "needs a fix / has an objection" state — there is no separate
  `changes_requested`.

The semantic hash covers the approved contract: CEL (canonicalized), the unit's
`title` + `rationale`, and the referenced observable/event meaning (schema +
`description`, inlined). Changing a referenced schema or description makes dependent
behaviors stale automatically. Module/flow hashes are members/order +
title/rationale/glossary only (non-cascade): editing a member behavior does not
stale the module — `bspec status` shows a per-module rollup instead.

## CLI

```bash
bspec init [path]                           # scaffold bspec.json (review-state file)
bspec validate [path] [--json] [--strict]   # schema + reference + CEL checks (exit 1 on error)
bspec review [--module M] [--kind K] [--status S]   # interactive; only command that writes review decisions
bspec view [--module M] [--kind K] [--status S]     # read-only browse of all cards (writes nothing)
bspec status [path] [--json]                # per-kind + per-module status
bspec doc [path] [--module M]               # markdown + mermaid export (GitHub/sharing)
```
