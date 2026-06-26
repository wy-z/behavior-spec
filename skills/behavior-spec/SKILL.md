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

- Behavior Spec files are `*.bspec.json` (matched by `specGlobs` under the project root) — these you may write.
- Review decisions live in `bspec.json` at the project root.
- **Never edit `bspec.json`.** Only `bspec review` may create review decisions.
- `bspec.json` declares `lang` (default `en`): the language for all human-readable
  text (`title`/`summary`/`comment`) in `*.bspec.json`. Write descriptive text in
  that language; leave ids, CEL, and schemas unchanged.
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

1. `bspec init` to scaffold `bspec.json` + an example spec.
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
7. Record one or more `origin` entries (where you derived it).
8. Keep the machine-checkable constraint in CEL/schema — `summary` explains a rule
   for humans (and is hashed), but must never be the *only* place a constraint lives.
9. If the code is ambiguous, do **not** invent intent — leave the behavior out
   or describe the ambiguity in an `origin.note`, and tell the user.

After writing files: `bspec validate --json`, and fix **every** error before review.

## Descriptive text: write for a novice reviewer (Feynman)

Humans approve from the review card, which shows `title` + `summary` next to the
raw CEL and origin. Assume the reviewer knows nothing about this module:

- `title` — a short, scannable label (a few words).
- `summary` — a **self-contained, plain-language explanation** of what the rule
  does: restate the CEL in words and fold in the context needed to judge it in one
  read. Every review-unit kind (module / behavior / invariant / flow) takes one.

Example (behavior):
- `title`: `"Approve a pending spec"`
- `summary`: `"When a spec that is still pending is approved, its recorded status
  must become approved — only then may a downstream agent implement it."`

For fields that never reach the card, add depth that still helps file readers and
`context` consumers — `observable.description`: units, allowed values,
computed-vs-stored nuances.

`summary` is part of the semantic hash, so editing it re-opens review — keep it
accurate. It restates the rule in plain words; the machine-checkable constraint
still lives in CEL (rule 8). Write all descriptive text in the project's `lang`.

Define any shared or non-obvious term once in the file-level `glossary`
(`{ "term": "definition" }`); it is shown on the card and exported in `context`,
so a reviewer never meets an undefined word.

**Mandatory novice self-review pass.** Before handing specs to a human, re-read
every `summary` as someone who has never seen this codebase. For each, list what a
layperson could not understand (unexplained jargon, missing context, implied prior
knowledge) and rewrite until nothing is left. The bar is one inversion test:

> A reviewer who has never read the code can decide approve/reject from the card alone.

If a card fails that test, the summary or glossary is incomplete — fix it first.

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

Never use raw spec files as the implementation target. Load only approved,
fresh context:

```bash
bspec context --module <module-id> --approved      # emits JSON
```

Implement the returned approved behaviors and invariants exactly. Do **not**
implement `pending`, `stale`, `rejected`, `deferred`, or `changes_requested`
items as requirements. New requirements: edit the Behavior Spec first, get it
approved, then implement.

## Prohibited actions

Never:
- write or modify `bspec.json` / any review record;
- mark a behavior approved, or fabricate a decision or semantic hash;
- hide validation errors;
- silently replace an approved behavior;
- encode an implementation choice as observable product behavior;
- treat current source code as intended behavior without human review.
