---
name: behavior-spec
description: >
  Use when capturing, reviewing, or implementing what a system MUST do as
  observable behavior (not implementation) — specifying a feature/API/service/job/
  strategy's required behavior, getting it human-reviewed before coding, or
  creating/editing `*.bspec.json` files. Keywords: behavior spec, bspec, spec a
  feature, review behavior not code, approved spec, observable behavior.
---

# Behavior Spec workflow

Use this skill whenever the user asks to:
- discover product or system modules;
- document observable behavior (not implementation);
- generate or update Behavior Spec (`*.bspec.json`) files;
- review system behavior instead of implementation code;
- implement functionality from approved Behavior Specs.

A Behavior Spec answers one question per rule: **in some observable context,
when an event happens, which observable results MUST the system produce, and
which conditions MUST always hold.**

## Source of truth

- The **bspec root** is whatever folder holds `bspec.json` (the review-decisions
  file). Keep your `*.bspec.json` files under it — commonly the same folder. The
  root need not be the repo root; a subdirectory like `docs/behavior/` is fine.
- Behavior Spec files are `*.bspec.json` (matched by `specGlobs` under the bspec
  root) — these you may write.
- **Never edit `bspec.json`.** Only `bspec review` may create review decisions.
- `bspec.json` declares `lang` (default `en`) **in this one place**: the language
  for all human-readable text (`name`/`title`/`rationale`/`description`) in
  `*.bspec.json`. Write that text in that language; leave ids, CEL, and schemas
  unchanged.
- For a non-English `lang`, also fill `bspec.json`'s `glossary` with the localized
  **type words** — `module`/`behavior`/`invariant`/`flow`/`interface`/`event`/
  `observable`/`input`/`output`/`state`/`parameter` (e.g. `"interface": "接口"`).
  `bspec review` prepends each unit's raw `[kind][direction]` tag and looks these up
  to show `[接口][输入]` instead of `[interface][input]`; missing keys fall back to
  the raw word. This is project config (in `bspec.json`, **not hashed**) — distinct
  from a module file's domain `glossary` (term definitions, hashed into the module).
- Current source code is an *observation source*, not automatically the intended
  behavior. Do not promote code behavior to a spec without human review.

## The tool is deterministic — never guess what it would say

`bspec` does no LLM work. Always run it instead of reasoning about validity:

```bash
bspec status --json        # what is pending / stale / approved
bspec validate --json      # schema + reference + CEL type errors
```

Before changing specs, read from `status --json`: existing module ids, which
behaviors/invariants are `approved`, and which are `pending`, `stale`, or
`changes_requested` (with their comments).

## Module discovery (when no specs exist yet)

1. **Ask the human which language** the specs should be written in, then
   `bspec init [<dir>] --lang <code>` to scaffold `bspec.json` into `<dir>`
   (default cwd; e.g. `bspec init docs/behavior` to keep specs there).
   For a non-English `lang`, `init` pre-fills the type-word `glossary` with English
   placeholders — **translate each value** (e.g. `"interface": "接口"`); see
   *Source of truth* for how the tool uses them.
2. Inspect user-visible capabilities and external-system responsibilities.
3. Do **not** turn code packages (`utils`, `hooks`, `services`, `repositories`)
   into modules unless they are independently reviewable system capabilities.
4. Create module stubs first (one `<name>.bspec.json` per module, with
   just the `module` block). Keep module ids stable.
5. `bspec validate --json`, then ask the human to review scope:
   `bspec review --kind module`.
   Do not generate detailed specs for rejected modules.

## Behavior generation (one module at a time)

For each behavior:
1. Give it a globally stable id.
2. Declare exactly **one** trigger event in `when.event` (an input event).
3. Put preconditions in `given` (CEL over `before`, `params`).
4. Put trigger-payload conditions in `when.where` (adds `trigger`).
5. Put every required result in `then` — each entry is exactly one of
   `assert` / `emit` / `forbid`; all entries are mandatory (AND).
6. Reference only declared observables, parameters, events, interfaces.
7. Optionally record `origin` entries (non-normative provenance — where you derived it).
8. Keep the machine-checkable constraint in CEL/schema — `title`/`rationale` state
   the rule for humans (both hashed), but must never be the *only* place a
   constraint lives.
9. If the code is ambiguous, do **not** invent intent — leave the behavior out
   or describe the ambiguity in an `origin.note`, and tell the user.

Optionally set `actor` — who initiates the rule (a human role, external system, or
scheduler) — and define that term in the file `glossary`. It scopes *who* the
requirement is about for review; omit it for actorless rules. It is hashed when
present, so editing it re-opens review.

After writing files: `bspec validate --json`, and fix **every** error before review.

## Writing name / title / rationale (every card stands alone)

A human approves each review unit from one card. Make it self-standing: a reviewer
who has read no sibling unit and no code can decide *agree or reject*. Standard
requirements practice — `name` labels it, `title` is the requirement, `rationale`
is the why, `glossary` defines terms, CEL is the formal check (INCOSE *Guide to
Writing Requirements*: separate rationale from the requirement; ISO/IEC/IEEE 29148:
singular, complete, unambiguous, verifiable).

### name — a short human label (required, every object)

One short noun phrase in the project `lang` (`批准规格`, `Open long`, `评审命令`).
It is the reviewer's handle when the `id` is cryptic, and the only label shown in
compact places (tables, diagram nodes). **Do not** write a type tag and **do not**
translate one — the tool prepends the raw `[kind][direction]` (e.g. `[event][input]`,
`[observable][state]`) at display time. Don't just repeat the id. Cosmetic (not hashed).

### title — the requirement, as an EARS sentence

Required for `behavior`/`invariant` (the actual rules); optional for `module`/`flow`
(use it for scope / an ordered outcome). One active-voice sentence; obligation word
`must` / `must not` / `only` (not "shall", not a label, fragment, or `A → B`). Pick
the EARS pattern by kind and write it in the project `lang`:

| kind | EARS pattern | template |
|---|---|---|
| behavior (event) | event-driven | `When <event>[ and <where>], <system> must <result>.` |
| behavior + `given` | state + event | `While <given>, when <event>, <system> must <result>.` |
| behavior `forbid` | unwanted behaviour | `If <event>, then <system> must not <result>.` |
| invariant (always) | ubiquitous | `<system> must always <constraint>.` |
| invariant + `while` | state-driven | `While <state>, <system> must <constraint>.` |
| flow | condition → action | `When <workflow> runs, <system> must <ordered outcome>.` |
| module | event / ubiquitous at scope | `When <actor needs capability>, <module> must <bounded outcome>.` |

One *thought* per title (INCOSE singularity): if "and/or" joins two results, split
into two units. Completeness beats length. **Hashed** — it is the prose a layperson
approves, so editing it re-opens review.

### rationale — the why (2–4 plain sentences, required)

Not a paraphrase of the title or CEL — the *why*. Plain language: active voice,
present tense, one idea per sentence. In order:
1. the state/mode/request this unit is about (restate the domain condition in
   plain words if needed to stand alone; never transcribe the CEL);
2. when the rule applies and when it does not;
3. the observable mistake or unsafe outcome it prevents.

Omit (describe behaviour, not mechanism): implementation steps, UI/CLI mechanics,
"see <other unit>" references. No em-dash asides, no meta-framing. **Hashed.**

### description — what a definition is (optional: interface/event/observable)

The channel/value semantics a reviewer needs to understand a referencing rule
(e.g. what an observable's states mean). Hashed *when referenced* by a reviewed rule.

### glossary — define shared terms once

Repeated or non-obvious terms go in `glossary` (INCOSE: define terms in a
glossary); they render on every card, so no word is left undefined. CEL stays the
exact rule — name a literal (`approved`, `strict`) in prose only when that value
is what's compared.

**Acceptance gate** (ISO 29148 *complete* + INVEST *independent*): if a cold
reviewer cannot decide agree/reject from the card alone, it is not done — fix the
name/title/rationale, don't lean on siblings or code. `title` and `rationale` are
hashed, so editing them re-opens review.

## Validator-enforced rules — let the tool teach them

Id, CEL, and JSON-Schema-subset rules are all caught by `bspec validate` with
clear messages, so fix every error it reports rather than memorizing them. The
one that bites most: **observable/parameter ids use dots only (no hyphens) and
none may prefix another; every other id uses hyphens, never underscores; payload
property names are CEL identifiers (`exit_code`).** Full rules + CEL namespace
matrix + schema subset: `references/cheatsheet.md`.

## Review (humans only)

```bash
bspec review --module <module-id>      # interactive: [a]pprove [c]hanges [r]eject [d]efer
```

The review cards and `bspec doc` show diagrams for flows (an ordered step
pipeline) and modules (a boundary I/O / context graph). These are **derived from
structure, never authored** — there is no diagram field; keep `steps`,
`interface`, and `direction` correct and the diagram follows. To read or share a
module as rendered diagrams (GitHub / VS Code render the mermaid):

```bash
bspec doc --module <module-id>         # markdown + mermaid to stdout
```

The human owns all approval decisions. After review:

```bash
bspec status --json
```

For each `changes_requested` item: read the comment, edit the behavior
(preserve its id if it is still the same conceptual behavior), re-validate, ask
for another review. For `rejected` items: remove them, or replace only when the
reviewer explicitly asks for a different behavior.

A spec becomes `stale` automatically when its normative content — or the schema
of an observable/event it references — changes. Stale items need re-review.

## Implementing code from specs

The `*.bspec.json` files are the implementation target — read the behaviors and
invariants directly and implement them exactly. Review state does **not** gate
what you may read; it is the human reviewer's incremental-review ledger (which
units are new or changed since they last approved), not a filter on consumption.

New requirements: edit the Behavior Spec first, then implement — never encode a
new requirement in code without writing it into the spec.

## Prohibited actions

Never:
- write or modify `bspec.json` / any review record;
- mark a behavior approved, or fabricate a decision or semantic hash;
- hide validation errors;
- silently replace an approved behavior;
- encode an implementation choice as observable product behavior;
- treat current source code as intended behavior without human review.
