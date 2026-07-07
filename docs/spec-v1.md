# bspec — Behavior Spec v0.1 Implementation Specification

> Status: **v0.1 freeze candidate (first version)**
> This document is the normative implementation spec. It supersedes and freezes the v0.1 design notes.
> Scope boundary: a Behavior Spec describes **observable semantics only**, never implementation. Spec files are written by a Code Agent; **review state records only human decisions** — by keypress in `bspec review`, or by the human's explicit delegation (§12).

---

## 0. Kernel definition

> In some observable context, when an event happens, which observable results the system **must** produce; and which conditions must **always** hold.

UI apps, API services, quant strategies, background jobs, and data pipelines are instances of this one kernel. Domain differences live only in the *declared* observables, events, interfaces, and the contents of CEL expressions — never in new behavior syntax.

Two hard boundaries:
1. A Behavior Spec describes observable semantics, not implementation.
2. Spec files may be Agent-written; a review decision is recorded only from a human decision — the human's keypress in `bspec review`, or the human's explicit delegation (§12) — never on the agent's own initiative.

---

## 1. Conceptual model (8 object types)

| Concept | Meaning |
|---|---|
| **module** | Human review boundary. NOT a code package. |
| **interface** | Observable boundary where input is received or output produced. |
| **observable** | A state value or parameter a reviewer cares about. |
| **event** | An input or output occurring at a point in time. |
| **behavior** | One rule: `given + when → then`. |
| **invariant** | A condition that must always hold: `while → assert`. |
| **flow** | Ordered references to behaviors. Navigation/review aid only. Non-normative. |
| **origin** | Where the Agent derived a spec from. Review metadata only. Non-normative. |

Anything a human must review **must** be modeled as an observable or an event. Anything not in those two models is an implementation detail and stays out of the spec.

---

## 2. File layout

```
<project-root>/               # the directory that holds bspec.json
├── bspec.json                # Review state (decisions human-gated, §12); its location marks the root
├── *.bspec.json              # Behavior Spec files (Agent-writable), anywhere under the root
└── skills/
    └── behavior-spec/        # Agent Skill (optional in repo)
        ├── SKILL.md
        └── references/
```

- The **project root is the nearest ancestor directory containing `bspec.json`** (`bspec` walks up from the cwd / given path to find it). Spec files are matched by `specGlobs` (default `**/*.bspec.json`) resolved relative to that root — a `behavior/` subdirectory is one convention, not a requirement.
- All matched `*.bspec.json` files load into **one global symbol namespace** (see §11).
- `bspec.json` holds: `lang` (default `en`), the optional type-word `glossary` (§12), `specGlobs`, review decisions, reviewed semantic hashes, time, comment. Nothing else.
- **Review state is never written back into Behavior Spec files.**

---

## 3. Behavior Spec document structure

One module per `*.bspec.json` file.

```json
{
  "$schema": "https://wy-z.github.io/behavior-spec/v1/schema.json",
  "bspecVersion": "v1",
  "module":      { },
  "glossary":    { },
  "interfaces":  [],
  "observables": [],
  "events":      [],
  "behaviors":   [],
  "invariants":  [],
  "flows":       []
}
```

Meta-schema: **JSON Schema Draft 2020-12**. Every object sets `"unevaluatedProperties": false`. Unknown fields fail validation (a misspelled `paylodSchema` is an error, never silently accepted).

All `*.bspec.json` files share **one global namespace**; cross-file references resolve globally. (Module-scoped namespaces / `imports` are deferred to v0.2.) `glossary` is an optional `{ term: plain-language definition }` map for the file's shared vocabulary; it is surfaced in review cards and is part of the module's semantic hash.

---

## 4. Identifiers

### 4.1 General id regex (module, interface, event, behavior, invariant, flow)

```
^[a-z][a-z0-9_]*(?:[.-][a-z0-9_]+)*$
```

Examples: `theme`, `orders`, `account.authentication`, `trading.ma-cross`, `order_created`.
Both `_` and `-` are allowed here; only observable/parameter ids (§4.2) forbid `-`.

### 4.2 CEL-addressable id regex (observable, parameter)

Because observables/parameters become nested CEL fields (§7.2), their ids and the field names inside their schemas must be valid CEL identifiers:

```
observable/param id:   ^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$     (dot-separated, NO hyphen)
schema property name:  ^[a-z][a-z0-9_]*$                            (CEL identifier)
```

Examples: `portfolio.gross_exposure`, `orders.count`, `navigation.current_page`.

### 4.3 Uniqueness & collision rules

- Ids are unique **per kind** across the whole project (all observables unique, all events unique, …).
- **Observable/parameter prefix-collision is an ERROR**: no observable/parameter id may be a dot-boundary prefix of another (e.g. `portfolio` and `portfolio.gross_exposure` cannot coexist). This keeps the CEL namespace tree unambiguous (§7.2).
- The same string may be reused across different kinds (refs are kind-typed), but tools warn on cross-kind id reuse.

---

## 5. Object field definitions (frozen)

Normative fields are included in the semantic hash (§13). `name` is a short human
label — required on **every** object, **cosmetic** (not hashed): the tool prepends
the raw `[kind][direction]` tag at display time, so the tag is never authored.
`title` is the EARS requirement — **normative** (hashed), required on
`behavior`/`invariant`, optional on `module`/`flow`. `rationale` is the why —
required + **normative** on review units. Definition `description` is optional and
hashed **when the definition is referenced** by a review unit (its meaning shapes
that approval). `origin.note` is cosmetic. `glossary` (file-level) is hashed into
the module.

### module
```json
{ "id": "trading.ma-cross", "name": "…", "title": "…", "rationale": "…" }
```
`id` + `name` + `rationale` required (`rationale` non-empty, **normative**). `title`
optional (scope sentence; normative when present).

### glossary (file-level, optional)
```json
"glossary": { "fresh": "approval still valid: stored hash == current hash", "…": "…" }
```
A `{ term: plain-language definition }` map shared by the file's units. Surfaced in review cards; part of the **module** semantic hash.

### interface
```json
{ "id": "trading.market-bars", "name": "…", "description": "…", "direction": "input" }
```
`id` + `name` + `direction` required. `direction` ∈ `input | output | bidirectional`. `description` optional (hashed when referenced).

### observable
```json
{ "id": "portfolio.gross_exposure", "name": "…", "role": "state", "valueSchema": { "type": "number", "minimum": 0 } }
```
`id` + `name` + `role` + `valueSchema` required. `role` ∈ `state | parameter`. `description` optional (hashed when referenced). `valueSchema` is a restricted JSON Schema (§6).
- `role: state` → appears in `before` / `after` / `current` namespaces.
- `role: parameter` → appears in `params` namespace.

### event
```json
{ "id": "market.bar.closed", "name": "…", "description": "…", "direction": "input",
  "interface": "trading.market-bars", "payloadSchema": { "type": "object", "additionalProperties": false, "required": [...], "properties": {...} } }
```
`id` + `name` + `direction` + `interface` + `payloadSchema` required. `direction` ∈ `input | output`. `interface` must resolve; its direction must be compatible (`input` event ⇒ interface `input|bidirectional`; `output` event ⇒ interface `output|bidirectional`). `payloadSchema` must be a restricted object schema with `additionalProperties:false`. `description` optional (hashed when referenced).

### behavior
```json
{ "id": "trading.ma-cross.open-long", "name": "…", "title": "…", "rationale": "…",
  "actor": "…",
  "given": { "cel": "…" },
  "when":  { "event": "market.bar.closed", "where": { "cel": "…" } },
  "then":  [ { "assert": { "cel": "…" } }, { "emit": { "event": "…", "where": { "cel": "…" } } }, { "forbid": { "event": "…" } } ],
  "origin": [ { "kind": "code", "uri": "…" } ] }
```
- `name` required (short label). `title` required (EARS requirement; **normative**). `rationale` required (non-empty why; **normative** — §13).
- `actor` optional: who initiates the rule (a human role, external system, or scheduler). Define the term in `glossary`. **Normative when present** (hashed) — it scopes who the requirement is about; omit for actorless rules.
- `given` optional (no precondition ⇒ omit).
- `when` required: exactly **one** trigger `event` (must be an **input** event); `where` optional.
- `then` required, **≥1 entry**; each entry is exactly one of `assert | emit | forbid`.
- `origin` optional, non-normative.

### invariant
```json
{ "id": "trading.risk.max-gross-exposure", "name": "…", "title": "…", "rationale": "…",
  "while":  { "cel": "…" },
  "assert": { "cel": "…" },
  "origin": [ … ] }
```
`name` + `title` + `rationale` + `assert` required (`title`/`rationale` **normative**). `while` optional (always-hold ⇒ omit).

### flow
```json
{ "id": "trading.trade-cycle", "name": "…", "title": "…", "rationale": "…", "steps": [ "behavior.id.a", "behavior.id.b" ] }
```
`name` + `rationale` + `steps` required (`steps` order **is** normative; `rationale` **normative**). `title` optional (normative when present). Flows declare **no** new conditions, outputs, or rules.

### origin (non-normative)
```json
{ "kind": "code", "uri": "src/x.ts", "note": "…" }
```
`kind` ∈ `code | config | doc | runtime | human | inference`. File-level provenance — answers only "why did the Agent generate this", never "is the implementation correct".

---

## 6. JSON Schema subset for `valueSchema` / `payloadSchema`

To make static CEL type-checking deterministic, schemas that CEL reaches are restricted:

**Allowed**
- `type`: `string | integer | number | boolean | object | array`
- `object` with `properties` and **`additionalProperties: false`** (required)
- `array` with a single `items` schema
- `enum` (paired with `type`; enum membership is documentation/data-validation only, CEL sees the base type)
- Annotations: `minimum | maximum | exclusiveMinimum | exclusiveMaximum | minLength | maxLength | pattern | minItems | maxItems | format | required`

**Disallowed in v0.1 (ERROR)**
- `oneOf | anyOf | allOf | not | if/then/else`
- `$ref`, `patternProperties`, `additionalProperties: true` (or omitted on objects)
- tuple `items` (array form), `type` as an array, `type: "null"`, `nullable`

**Nullability**: there is no null type. An optional value is expressed by leaving the field out of `required`; in CEL it is guarded with `has()`. (Resolves the null/presence gap.)

**Discriminated unions.** v0.1 has no union types. Model variants the idiomatic way: one closed event/observable per variant (e.g. `order.market.created` vs `order.limit.created`), which also fits the one-trigger-per-behavior rule. **Known limitation** (codex round 2): a single *legacy* polymorphic payload that must be modeled verbatim — one event whose field is genuinely `A | B` — cannot be expressed in v0.1; a typed `dyn` escape hatch is deferred to v0.2.

### 6.1 JSON Schema → CEL type mapping

| JSON Schema | CEL type |
|---|---|
| `string` (incl. enum of strings) | `string` |
| `integer` | `int` |
| `number` | `double` |
| `boolean` | `bool` |
| `object` + `properties` (`additionalProperties:false`) | object type with typed fields |
| `array` + `items: T` | `list(T)` |

**Numeric literals (frozen — narrow literal widening):** `integer→int`, `number→double`. CEL does not implicitly convert between `int` and `double` for **variables**, and bspec keeps that strict for variable-vs-variable comparisons. The single relaxation: an **integer literal is accepted where a `double` is expected** — literals only, never variables, and never `double`-literal→`int` (which would lose precision). A pre-typecheck AST pass retypes integer-literal nodes to `double` against the expected operand type, so both `before.orders.count == 0` and `before.portfolio.gross_exposure <= 10` type-check. Any residual mismatch (a variable-vs-variable int/double clash) is an ERROR whose message states the exact fix; authors bridge with the whitelisted `int()` / `double()` conversions. Convention: prefer `number` for measures, `integer` only for true counts. (Consensus with codex round 2: broader auto-coercion rejected — it would weaken static type clarity.)

---

## 7. CEL semantics

All expressions are **CEL** (parsed by celpy). Every expression must **parse**, **type-check**, and **return `bool`**, else validation fails.

### 7.1 Namespaces and per-clause usage matrix

| Namespace | Contents |
|---|---|
| `before` | observables (role `state`) before the event |
| `after` | observables (role `state`) after the behavior completes |
| `current` | observables (role `state`), for invariants |
| `params` | observables (role `parameter`) |
| `trigger` | the input event payload |
| `emitted` | the expected output event payload |

| Clause | Allowed namespaces |
|---|---|
| `given` | `before`, `params` |
| `when.where` | `before`, `params`, `trigger` |
| `then.assert` | `before`, `after`, `params`, `trigger` |
| `then.emit.where` | `before`, `after`, `params`, `trigger`, `emitted` |
| `then.forbid` | (no expression in v0.1) |
| `invariant.while` | `current`, `params` |
| `invariant.assert` | `current`, `params` |

Using a disallowed namespace in a clause is an ERROR (e.g. `after` in `given`, `emitted` outside `emit.where`).

### 7.2 Path resolution & typing model (D1 — frozen)

CEL parses `before.portfolio.gross_exposure` as nested **field selection**, not as a flat identifier. So each namespace is exposed to the type-checker as a **nested object type** built from the declared dotted ids:

- For each namespace, split every in-scope observable/parameter id on `.` and build a tree. Each leaf is the observable's CEL type (§6.1). Each interior node is an object type. (Same technique Kubernetes uses to derive CEL object types from OpenAPI schemas.)
- At a leaf whose `valueSchema` is itself an `object`, the schema's fields are spliced in, so field access continues into the value (e.g. `current.theme_feed.items` → observable `theme_feed`, then field `items: list`, then `.all(...)`).
- The prefix-collision ban (§4.3) guarantees no path is simultaneously an interior node and a leaf, so resolution is unambiguous.
- `trigger` / `emitted` types are built directly from the event `payloadSchema`.

Implementation note: Python has no cel-go-grade static checker, so bspec **owns the checker**. celpy parses each expression into a Lark tree; bspec walks that tree, resolving each dotted path against this nested type built from the symbol table, enforcing per-clause namespaces and the function whitelist. The tool never *evaluates* expressions.

### 7.3 Function / macro whitelist (frozen)

- Operators: `&& || !`, `== != < <= > >=`, `+ - * / %`, `in`, ternary `?:`
- Macros: `has()`, `all`, `exists`, `exists_one`, `map`, `filter`
- Functions: `size()`, `startsWith`, `endsWith`, `contains`, `matches` (RE2), and the numeric conversions `int()`, `double()`
- **Disallowed**: timestamp/duration/`now`-style and any non-deterministic function, custom functions, `cel.bind`. (Determinism is mandatory.)

### 7.4 No execution engine (D3 — frozen)

The validator never evaluates behaviors. `after` is typed from the **same** observable symbol table as `before`; there is no state-transition computation in v0.1. **Temporal satisfiability is unchecked** — the tool does not verify that a `given`+`when` is reachable or that an `after` assertion is achievable. That is the human reviewer's concern.

---

## 8. Behavior & invariant semantics

A behavior means:

```
G(before, params) ∧ W(trigger, before, params)  ⇒  T(after, emitted, trigger, before, params)
```

- **Multiple `then` entries = conjunction**: all must hold.
- `assert`: after the behavior, the asserted condition over observables must hold.
- `emit`: the system **must produce at least one** output event of `event` for which `where` holds.
- `forbid`: the system **must not produce any** output event of `event`. v0.1 `forbid` is **event-type-level only** (no `where`; deferred to v0.2).
- Every `then` clause is **mandatory**. There is no `SHOULD`/`MAY`/"usually". Uncertainty stays in a review comment or an Agent proposal, never in an approved spec.
- One behavior = one trigger event = one business reaction. ("Create the order, and return its id" = one reaction; "create order + send marketing email + retrain model" = three behaviors.)

An invariant means:

```
While C(current, params) holds, assertion A(current, params) must always hold.
```

---

## 9. Conflict policy

v0.1 performs **no automated conflict detection** between CEL-predicated behaviors (that needs an SMT solver; out of scope) — conflict avoidance is the reviewer's responsibility. There is **no implicit priority** (no file order, specificity, or last-wins); if two rules could both fire under the same conditions, make their conditions mutually exclusive. Declarative `overrides` precedence is **deferred to v0.2** (removed from the v0.1 schema).

---

## 10. Validation rules

`bspec validate` outcomes. Default exit: `1` if any ERROR. `--strict` makes warnings also exit `1`.

### Errors
- JSON parse failure; meta-schema violation; any unknown field (`unevaluatedProperties`).
- Duplicate id within a kind; id regex violation; schema property name not a CEL identifier.
- Observable/parameter prefix-collision.
- Unresolved reference: `when.event` / `emit.event` / `forbid.event` → event; `event.interface` → interface; `flow.steps` → behavior.
- Direction misuse: `when.event` not `input`; `emit`/`forbid` event not `output`; event/interface direction incompatible.
- `behavior.when` without exactly one event; `behavior.then` empty.
- `valueSchema`/`payloadSchema` uses a disallowed/unknown construct, an untyped node, an array without `items`, an object without `additionalProperties:false`, or a `required` entry absent from `properties` (§6).
- CEL: parse error; result not `bool`; reference to an undeclared observable/param; reference to a nonexistent payload field; namespace not allowed in the clause; type error (incl. int/double literal mismatch).
- A review unit `rationale` missing/empty (meta-schema) or that merely repeats its `title`/`name`/`id` (stub-rationale); a `name` that merely repeats its `id` (stub-name).

### Warnings
- Declared but never referenced: observable / event / interface.
- A referenced observable / event with no `description` (its meaning is hashed when referenced, §13.2).
- `origin.uri` path not found on disk (origin is non-normative).
- Flow with `< 2` steps; module with no members.

### `--json` output
Machine-readable result for the Agent:
```json
{ "ok": false, "counts": { "module": 4, "behavior": 23, "invariant": 5, "flow": 1 },
  "errors": [ { "code": "cel.type", "unit": "behavior:…", "path": "then[0].emit.where", "message": "…" } ],
  "warnings": [ … ] }
```

---

## 11. Reference resolution

All spec files load into one global, kind-keyed symbol table: `(kind, id) → object`. References resolve globally:

| Reference | Target kind |
|---|---|
| `when.event`, `emit.event`, `forbid.event` | event |
| `event.interface` | interface |
| `flow.steps[]` | behavior |
| CEL path in a namespace | observable / parameter (longest dot-prefix, §7.2) |

Cross-file references are permitted in v0.1 (global namespace).

---

## 12. Review state file `bspec.json`

```json
{
  "$schema": "https://wy-z.github.io/behavior-spec/v1/review-state.schema.json",
  "version": "0.1.0",
  "lang": "en",
  "specGlobs": [ "behavior/**/*.bspec.json" ],
  "reviews": {
    "behavior:trading.ma-cross.open-long": {
      "semanticHash": "sha256:90bf32…",
      "decision": "disputed",
      "reviewedAt": "2026-06-26T14:23:00-07:00",
      "comment": "Order should be produced at the next bar's open, not on this bar's close."
    }
  }
}
```

- Review record key: `"<kind>:<id>"` where kind ∈ `module | behavior | invariant | flow`.
- `decision` ∈ `approved | rejected | disputed`. **No `pending`/`stale` stored** — both are computed (§14).
- `reviewedAt` = RFC 3339.
- `comment` optional, **except required on `disputed`** (a dispute is nothing without its reason).
- **`disputed`** records a reviewer's substantive *reservation* rather than an approval — "reviewed, not approved; here is the concern." It is a stored decision, hash-bound like any other (so any spec change drifts it to `stale`), and is surfaced in `bspec review`'s default set so the human resolves it (an approve/reject keypress overwrites it). Its typical author is a delegated agent (below); it never counts as approval.
- `lang` = language of all human-readable text (`name`/`title`/`rationale`/`description`/`comment`) across the project's `*.bspec.json`; default `en`. Stored **only here**. Advisory metadata; not machine-enforced. Authors write that text in this language.
- `glossary` (optional) = a project-level `{ type-word: localized }` map (`interface→接口`, `input→输入`, …). `bspec review` looks it up to localize the `[kind][direction]` tag it prepends to each unit's `name`; missing keys fall back to the raw word. **Not hashed** (cosmetic project config) — distinct from a module file's domain `glossary` (§5), which is hashed into the module.
- **Reviewer identity is not stored** — git history is the authoritative record of who recorded each decision.
- **By default only `bspec review` writes review decisions.** The one exception is explicit human delegation: the agent may then record, for **`pending` units only**, an `approved` **or** `disputed` decision — live hash copied verbatim, `comment` prefixed `agent-approved:` / `agent-disputed:`, never overwriting an existing record (protocol: `skills/behavior-spec/SKILL.md` *Assisting a large review*; rationale: `docs/design/2026-07-01-agent-assisted-review.md`). A dispute only flags a concern — it approves nothing — so it is not bound by the low-stakes exclusion that gates approval. The agent never fabricates a decision, hash, or time on its own initiative.
- **Module records are scope-only.** A `module:<id>` record approves the module's membership/scope, **not** its rules. Rule-level approval is strictly per behavior/invariant; `module:<id> == approved` must never be read as "the rules are approved".

---

## 13. Semantic hash (D6 + canonicalization — frozen)

A review unit becomes stale when its **normative** content changes — including the prose a layperson approves: the EARS `title` and the `rationale`, plus a referenced definition's `description` (its meaning shapes the approval). Cosmetic changes (formatting, property order, `name`, `origin`/`origin.note`) must **not** invalidate an approval.

### 13.1 CEL canonicalization
Canonical CEL = a normalized **S-expression** emitted from the celpy Lark parse tree (parentheses unwrapped; whitespace/comments dropped by the grammar). String literals keep their raw text so distinct values can never collide. Cosmetic changes do not change the hash; any operator/operand change does. Because the tree is parser IR (not a stable AST), the celpy version is pinned and the canonicalizer is golden-tested.

### 13.2 Per-unit normative payload

**behavior**
```
{ kind:"behavior", id, title, rationale,
  given:  <canonCEL|null>,
  when:   { event, where:<canonCEL|null> },
  then:   [ ordered: {assert:<canonCEL>} | {emit:{event, where:<canonCEL|null>}} | {forbid:{event}} ],
  deps: {
    events:      { <id>: { direction, interface, description, payloadSchema:<JCS> } },   // trigger + emit/forbid events
    observables: { <id>: { role, description, valueSchema:<JCS> } }                      // every obs/param referenced by any CEL
  } }
```
Referenced observables are found by extracting namespace paths from each CEL AST and resolving them (§7.2). Dependency `deps` keys are sorted. A referenced definition's `description` is inlined, so editing it re-opens the referencing unit. `name` is never in the payload (cosmetic).

**invariant**: `{ kind:"invariant", id, title, rationale, while:<canonCEL|null>, assert:<canonCEL>, deps:{observables} }`

**flow**: `{ kind:"flow", id, title, rationale, steps:[ordered behavior ids] }` (non-cascade; `title` null when absent)

**module**: `{ kind:"module", id, title, rationale, glossary:{term:def}, members:{ behaviors:[sorted], invariants:[sorted], flows:[sorted] } }` (members + title/rationale + glossary only, non-cascade; `title` null when absent)

### 13.3 Hash
`semanticHash = "sha256:" + hex( SHA-256( JCS(payload, UTF-8) ) )`, where JCS = RFC 8785 JSON Canonicalization Scheme.

### 13.4 Why non-cascade for module/flow
A behavior change makes **that behavior** stale on its own. Module/flow hashes track only membership/order, so module/flow review = scope/sequence review and does not double-churn on every rule edit. Safety is preserved because staleness is tracked **per item** (§14), so a fresh module never implies its rules are fresh — `bspec status` surfaces a per-module rollup of contained pending/stale items for visibility.

> **Consensus note (codex, 2 rounds).** Cascade (module hash including member hashes) was initially proposed by the second opinion. It was **conceded as unnecessary** once module approval is given the narrow scope-only semantics above, combined with the mandatory `status` rollup and per-item staleness — these fully address the "misleading freshness" risk without re-opening a module on every rule edit.

---

## 14. `pending` / `stale` derivation

For each review unit `U` with current hash `H`:
- no record in `bspec.json` → **pending**
- record exists and `record.semanticHash == H` → the recorded decision (fresh)
- record exists and `record.semanticHash != H` → **stale** (regardless of prior decision; prior decision shown alongside)

**Dependency staleness propagates automatically**: a behavior's hash includes the schemas of every observable/event it references (§13.2). Change a referenced `valueSchema`/`payloadSchema` → the behavior's hash changes → the behavior becomes stale. No separate propagation pass is needed. (E.g. changing `orders.notional` from `number` to `integer` makes every behavior that references it stale.)

---

## 15. Review units

Only four kinds are review units: **module, behavior, invariant, flow**.

Supporting definitions (interface, observable, event) are **not** reviewed directly. They enter review two ways:
1. shown inline when reviewing a behavior that references them;
2. their schemas are folded into the referencing behavior's semantic hash (so a schema change re-opens the dependent behaviors).

---

## 16. CLI

All commands are **fully deterministic — no LLM, no network for core ops**.

### `bspec init [path] [--lang <code>]`
Scaffold in `path` (default cwd): `bspec.json` (`lang` = `--lang`, default `en`; empty `reviews`, `specGlobs: ["**/*.bspec.json"]`). For a non-English `--lang`, also pre-fills `bspec.json`'s `glossary` with the type words as English placeholders to translate (§12). The directory holding `bspec.json` becomes the project root. Does not overwrite existing files.

### `bspec validate [--json] [--strict]`
§10. Human output:
```
✓ Parsed 4 module files
✓ 23 behaviors, 5 invariants
✓ All ids unique; all references resolve
✓ All CEL expressions compile and type-check
0 errors, 3 warnings
```

### `bspec review [--module <id>] [--kind behavior|invariant|flow|module] [--status pending|stale|approved|rejected|disputed]`
Interactive fullscreen review, one card at a time. The review card shows the `[kind][direction]` typed `name`, the EARS `title`, the `rationale`, the rule (GIVEN / WHEN / MUST), referenced terms, glossary, and — for flow/module — a derived diagram (flow pipeline / module I/O), all in human-readable form. Keys: `←`/`→` page between units, `↑`/`↓` (and the mouse wheel) scroll a card taller than the screen, `[a]` approve, `[r]` reject, `[c]` dispute (collects a reason), `[q]` or `Esc` quit; the same letter keys drive the non-interactive line-based fallback. Decisions are letters, never arrows — on the fullscreen alt-screen the mouse wheel is delivered as `↑`/`↓` (which scroll), so it can never fire a decision. Writes decisions (with current `semanticHash`, `reviewedAt`, optional `comment`) to `bspec.json`. **This is the only command that writes review decisions.**

### `bspec view [--module <id>] [--kind behavior|invariant|flow|module] [--status <status>]`
Read-only browse of the same cards — every unit by default, regardless of status, so approved work stays viewable. Same navigation/scroll keys as `review` minus the decision keys (`←`/`→` page, `↑`/`↓` scroll, `[q]`/`Esc` quit). Writes nothing; non-interactive stdin prints the cards in sequence.

### `bspec doc [--module <id>]`
Markdown + `mermaid` export (read-only) for sharing / GitHub: per module a context graph, each flow as a pipeline, and behaviors/invariants as rule text. Diagrams are **derived** from structure (`steps`, `interface`/`direction`); there is no diagram field to author.

### `bspec status [--json]`
Counts per kind per status, including computed `pending`/`stale`, plus a per-module rollup of contained item statuses.

---

## 17. Agent Skill (outline)

`skills/behavior-spec/` with `SKILL.md` + `references/`.

Responsibilities (Agent) vs the tool/human:
- **Agent**: scan project, create module stubs, generate/revise behaviors & invariants, run `bspec validate`, respond to human-raised `disputed` items, remove `rejected` items, record human-delegated batch approvals/disputes (§12), implement directly from the spec files.
- **Agent must NOT**: write or modify any review record on its own initiative (the sole exception is the human-delegated, pending-only batch protocol of §12), overturn an existing decision, change a semantic hash, hide validation errors, silently replace an approved behavior, encode implementation choices as observable behavior, or treat current source as intended behavior without human review.

Closed loop:
```
1. Agent scans project        →  2. Agent writes module stubs   →  3. bspec validate
4. Human reviews modules      →  5. Agent generates behaviors    →  6. bspec validate
7. Human reviews behaviors/invariants  →  8. Agent fixes human-raised disputes  →  9. Human re-reviews
10. Agent implements from the spec files  →  11. New requirement = edit spec first, then code
```

---

## 18. Implementation stack & layout (Python)

Installable CLI package, fully deterministic (no LLM, no network in core commands).

| Concern | Choice |
|---|---|
| Runtime | Python ≥3.11 (uv-managed venv) |
| JSON Schema (Draft 2020-12) | `jsonschema` (`Draft202012Validator`) |
| Expressions | `cel-python` (celpy) — **parse only**; bspec owns the checker over the Lark tree |
| CLI | `argparse` (stdlib) |
| Interactive review | stdlib prompt (`input`) |
| Canonical hash | `rfc8785` (JCS) + `hashlib.sha256` |

`cel-python` is **pinned exactly** (`==0.5.0`): its Lark parse tree is parser IR, not a stable AST, so an upgrade could silently churn semantic hashes. Bump only with canonicalization golden tests green.

```
src/bspec/
├── model.py        # 8 object types indexed + symbol table + module membership + glossary
├── loader.py       # glob + parse + schema-validate + duplicate detection + index
├── schema.py       # embedded meta-schema validation
├── checks.py       # references, directions, summaries, prefix, schema subset, unused
├── expression.py   # CEL: type model, namespace tree, Lark-tree checker, ref extraction, canonical S-expr
├── hashing.py      # normative extraction + canonical CEL + JCS + sha256 (module/flow non-cascade)
├── status.py       # pending/stale derivation + per-module rollup
├── review.py       # bspec.json read/write + interactive review/view (sole writer of review decisions)
├── diagram.py      # mermaid derivation: flow pipelines + module context graphs
├── doc.py          # markdown + mermaid export (bspec doc)
├── cli.py          # argparse: init / validate / review / view / status / doc
└── schemas/        # bspec.schema.json, review_state.schema.json
tests/              # schema, loader, checks, expression (CEL), hashing (golden+stability), review+status
```

---

## 19. Frozen decisions & deltas

> All core decisions were validated against a codex second opinion over two rounds. **D1** was reshaped in round 1 (nested CEL types via TypeProvider, not manual prefix-matching). **D5** (`overrides`) was subsequently **deferred to v0.2** and removed from the schema. **D6** stands non-cascade — codex initially favored cascade, then conceded it unnecessary in round 2. **P2/P4** confirmed in round 2. A later review-ergonomics round (also codex-reviewed) made the reviewer-facing prose required and part of the hash, added a file-level `glossary`, tightened schema typing, gated flow export, and removed the inert `participants`/`imports`/`overrides`. A final field-model round (codex-consensus) added a required cosmetic `name` (tool-derived `[kind][direction]` tag), renamed `summary`→`rationale`, made `title` a hashed requirement (required on behavior/invariant), hashed referenced-definition `description`, dropped `origin` line numbers, and removed observable `role: derived`. All rows below are consensus.

| # | Decision | Resolution |
|---|---|---|
| D1 | CEL path resolution | Nested CEL object types per namespace from dotted ids (cel-go native field selection); CEL ids = dot-separated CEL identifiers; prefix-collision = ERROR. |
| D2 | CEL ↔ JSON Schema typing | Restricted schema subset; objects require `additionalProperties:false`; no `oneOf/anyOf/$ref/null`. |
| D3 | No execution engine | Validate/typecheck only; `after` typed like `before`; temporal satisfiability unchecked. |
| D4 | emit/then semantics | `then` = conjunction; `emit` = ≥1 matching output; `forbid` = event-type-level (no `where`). |
| D5 | overrides | **Deferred to v0.2**; removed from the v0.1 schema (was inert metadata). |
| D6 | module/flow hash | Members/order + `title`/`rationale`/`glossary` only (non-cascade), scope-only module approval; per-unit staleness drives incremental review; `status` rollup for visibility. (codex-converged) |
| — | Nullability | No null type; `required` + CEL `has()`. |
| — | Numeric literals | `integer→int`, `number→double`; **narrow literal widening** (int-literal→double); strict for variables; `int()/double()` to bridge. |
| — | Discriminated unions | Decompose into one closed event/observable per variant; verbatim legacy polymorphic payloads deferred to v0.2 (`dyn`). |
| — | Hash canonicalization | CEL = normalized S-expr from the celpy parse tree; payload = JCS (RFC 8785) + SHA-256. |
| — | Dependency staleness | Propagates automatically through referenced schemas in the behavior hash. |
| — | Namespaces | `before/after/current` = state; `params` = parameter; per-clause matrix enforced. |
| — | Reviewer identity | Not stored; git history is the record of who decided. |
| — | Descriptive-text language | `bspec.json.lang` (default `en`); advisory; authors follow it. |
| — | name / title / rationale | Every object has a short `name` (cosmetic; tool prepends `[kind][direction]`). Review units need a `title` (EARS requirement) and `rationale` (why), both **in the semantic hash**. Stub `rationale` (== title/name/id) or stub `name` (== id) = ERROR. |
| — | Glossary | Optional file-level `{term:def}`; surfaced in cards; part of the **module** hash. |
| — | Schema strictness | Schema nodes must declare `type`; unknown keywords, missing array `items`, and `required` not-in-`properties` are ERRORs (no silent `dyn`). |
| — | participants / imports | **Removed** from the v0.1 schema (were inert); global namespace remains. |

### Deferred to v0.2 (explicitly out of v0.1 scope)
`participants` · `imports` / module-scoped namespaces · `overrides` & automated conflict detection (SMT) · `forbid.where` · `emit` exactly-once cardinality · multi/remote reviewer identity · cascading module hash · `oneOf/anyOf` and nullable schemas · runtime/test evidence, traces, screenshots · web review platform · drift detection.

---

## 20. v0.1 acceptance criteria

- [ ] Meta-schema validates all 8 object types with `unevaluatedProperties:false`; unknown fields fail.
- [ ] Loader builds one global kind-keyed symbol table from the project's `specGlobs` (default `**/*.bspec.json`).
- [ ] All references (§11) resolve or ERROR; direction/namespace misuse ERRORs.
- [ ] Observable/parameter prefix-collision ERRORs; CEL-id and property-name regexes enforced.
- [ ] Every CEL expression parses, type-checks against the §7.2 nested types, and must return `bool`; the §7.3 whitelist is enforced.
- [ ] Numeric literal widening applied (integer-literal→double, literals only); variable-vs-variable int/double mismatch still ERRORs.
- [ ] `then` conjunction, `emit` ≥1, `forbid` event-level, one-trigger/one-reaction all enforced.
- [ ] Every object has a `name`; review units have `title` + `rationale` (both in the hash); stub `rationale` (== title/name/id) and stub `name` (== id) rejected; file-level `glossary` surfaced in cards.
- [ ] Semantic hash is stable under formatting / `name` / `origin` changes, and changes under any normative edit (`title`, `rationale`, CEL operand, referenced schema or `description`, module/flow membership).
- [ ] `pending`/`stale` derived correctly; dependency-schema change marks dependents stale.
- [ ] `bspec init|validate|review|view|status|doc` behave per §16; among commands only `review` writes review decisions (`view` writes nothing).
- [ ] No LLM and no network in any core command.
```
