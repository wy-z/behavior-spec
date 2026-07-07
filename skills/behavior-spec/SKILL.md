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
- **Never write review decisions in `bspec.json`** — only `bspec review` (a human
  keypress) records them; sole exception: a human-delegated batch (*Assisting a
  large review*). The file's project config (`lang`, `specGlobs`, the type-word
  `glossary` below) is not a decision — setting it up is fine.
- `bspec.json` declares `lang` (default `en`) **in this one place**: the language
  for all human-readable text (`name`/`title`/`rationale`/`description`) in
  `*.bspec.json`. Write that text in that language; leave ids, CEL, and schemas
  unchanged.
- For a non-English `lang`, also fill `bspec.json`'s project `glossary` with the localized
  **type words** — `module`/`behavior`/`invariant`/`flow`/`interface`/`event`/
  `observable`/`input`/`output`/`state`/`parameter` (e.g. `"interface": "接口"`).
  `bspec review` prepends each unit's raw `[kind][direction]` tag and looks these up
  to show `[接口][输入]` instead of `[interface][input]`; missing keys fall back to
  the raw word. This is project config (in `bspec.json`, **not hashed**) — distinct
  from a module file's domain `glossary` (term definitions, hashed into the module).
- Current source code is an *observation source*, not automatically the intended
  behavior. Do not promote code behavior to a spec without human review.

## The tool is deterministic — never guess what it would say

`bspec` does no LLM work. Always run it instead of reasoning about validity.
If the CLI is not on PATH, install it first:
`uv tool install bspec --from git+https://github.com/wy-z/behavior-spec`

```bash
bspec status --json        # what is pending / stale / approved
bspec validate --json      # schema + reference + CEL type errors
```

Before changing specs, read from `status --json`: existing module ids, which
behaviors/invariants are `approved`, and which are `pending`, `stale`, or `disputed`
(with their comments).

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

After writing files, two gates are mandatory before you ask for human review — and
before any delegated approval — skip neither:
1. `bspec validate --json` — fix **every** error (schema, references, CEL types).
2. **Spec self-review** (see below) — the semantic checks the validator cannot make;
   resolve every finding.

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

## Spec self-review (mandatory gate — before human review)

This is **gate 2** from *Behavior generation*: run it on every new/changed unit before
asking for review — not optional, and not a command the human runs. `bspec validate`
checks schema, references, and CEL types — never *meaning*; this gate is the semantic
layer the tool cannot see. It is expression-quality only; it is **not** you approving
anything (see *Prohibited actions*). Check each unit against the card the human will see:

- **prose↔CEL fidelity** — does `title`/`rationale` describe exactly what the CEL and
  schema enforce? Flag any drift (`title` says "at most" but the CEL asserts `<`; the CEL
  adds a condition the prose omits).
- **EARS pattern** — `title` matches the pattern for its kind (table above).
- **singularity** — one thought per unit; if "and/or" joins two results, split it.
- **ambiguity** — every load-bearing term is pinned in `glossary` or the CEL, not left to
  interpretation ("fast", "valid").
- **standalone** — a cold reviewer can decide agree/reject from this one card.
- **cross-unit conflict** — no two units have overlapping `given`/`when` with
  contradictory `then`, and no duplicate intent.

Resolve each finding: on a `pending`, `disputed`, or `stale` unit, fix the
`*.bspec.json` and re-validate. On an `approved` or `rejected` unit, do **not** silently
edit it (editing an approved unit re-opens its review; a rejected one is replaced only
when the reviewer asks) — surface it. Any judgment call (is this really a conflict? is
this ambiguity acceptable?) — surface it with your recommendation; the human decides.

## Review (the human owns every decision)

```bash
bspec review --module <module-id>      # interactive: ←/→ unit, ↑/↓ scroll, [a]pprove [r]eject [c] dispute [q]uit
```

The review cards and `bspec doc` show diagrams for flows (an ordered step
pipeline) and modules (a boundary I/O / context graph). These are **derived from
structure, never authored** — there is no diagram field; keep `steps`,
`interface`, and `direction` correct and the diagram follows. To read or share a
module as rendered diagrams (GitHub / VS Code render the mermaid):

```bash
bspec doc --module <module-id>         # markdown + mermaid to stdout
```

The human owns every approval decision — made here by keypress, or delegated to the agent
for a scoped batch (*Assisting a large review*). After review:

```bash
bspec status --json
```

For each human-raised `disputed` item (its `comment` is *not* prefixed
`agent-disputed:`): read the comment, edit the behavior (preserve its id if it is
still the same conceptual behavior), re-validate, ask for another review. Leave
your own `agent-disputed:` items for the human to resolve. For `rejected` items:
remove them, or replace only when the reviewer explicitly asks for a different
behavior.

A spec becomes `stale` automatically when its normative content — or the schema
of an observable/event it references — changes. Stale items need re-review.

## Assisting a large review (only when the human asks)

When the human **explicitly asks** you to help clear a batch, you act as their delegate on
each `pending` unit in scope: **approve** the ones you can confidently clear, **dispute** —
with the reason — the ones you have a specific concern about, and leave the rest `pending`
for the human. Only on request — never on your own initiative, and never during authoring
(that is the self-review gate above, which approves nothing). Hard limits:

- **Work only from a list the human has seen.** They name the scope — a module, a kind, or
  an id list. A bare "help me review" or "all pending" is not a seen list: unless they
  handed you the exact ids, enumerate the units you would approve or dispute (after the
  limits below), show that list, and get their go-ahead before you write anything. Never
  sweep any scope unseen.
- **Only `pending` units — approve or dispute.** Touch a unit only if `bspec status --json`
  reports it `pending` (never reviewed). Never touch one that already carries a decision —
  `approved`, `rejected`, `disputed`, or `stale`: that is a human's call (or its history),
  and overturning it is the human's job, not yours.
- **Approve only expression-clear + low-stakes units.** The self-review checks above must all
  pass **and** the requirement must be mechanical and self-evidently right. Clarity ≠
  correctness: a well-worded rule can still be wrong to ship, so **never** agent-approve a
  unit whose behavior touches deletion or data loss, money/billing, auth/permissions,
  security or privacy, legal/compliance, external side effects, or anything irreversible or
  policy-laden — those go to the human even when perfectly worded. When in doubt, don't
  approve.
- **Dispute = a specific, articulable concern.** When a unit is *not* clearly approvable — a
  likely error, an ambiguity, a contradiction with another unit, or a high-stakes consequence
  worth surfacing — record `disputed` with the concern as its `comment`, rather than leave it
  silently `pending`, so the human sees your analysis when they review. Dispute is **not**
  gated by low-stakes: flagging a concern on a deletion/money/auth unit is exactly its purpose
  — it approves nothing, the human still decides. No specific concern, and not your call to
  make → just leave it `pending`.

There is no non-interactive command for either — you add the delegated entries to the
review-state file yourself:

1. `bspec status --json` — for each `pending` unit in scope read `units["kind:id"].hash`.
2. Add its entry to the `reviews` map of `bspec.json` (if the file is absent, confirm the
   intended bspec root with the human, then `bspec init` there first). Touch **only** the
   entries you are recording — never edit or drop another unit's record. To approve:

   ```json
   "behavior:<id>": {
     "semanticHash": "<the live units[key].hash from status --json, copied verbatim>",
     "decision": "approved",
     "reviewedAt": "<current local time, ISO-8601, e.g. 2026-07-04T10:30:00+08:00>",
     "comment": "agent-approved: <what you checked; why it is clearly correct and low-stakes>"
   }
   ```

   To dispute — the same entry with `decision: "disputed"` and the concern as its `comment`
   (**required** here: a dispute is nothing without its reason):

   ```json
   "behavior:<id>": {
     "semanticHash": "<the live units[key].hash, copied verbatim>",
     "decision": "disputed",
     "reviewedAt": "<current local time, ISO-8601>",
     "comment": "agent-disputed: <the specific concern the human must weigh>"
   }
   ```

   - Copy the **live** hash verbatim; never invent one. A wrong hash makes the record
     `stale` (the same guard as any drifted review), so the record can never outlive the
     spec it describes.
   - `comment` **must** begin with the literal `agent-approved:` or `agent-disputed:`. The
     record has no reviewer field, so that fixed prefix is the audit marker that lets anyone
     (or a later tool) tell your entries from a human's; after it, say why.
3. `bspec status --json` again — confirm each unit you touched now reads `approved` or
   `disputed` (not `stale`, which means a wrong hash; a crash means you malformed the JSON —
   fix it), and that no other unit's status changed.
4. Report which units you approved, which you disputed (with the concern), and which you
   left for the human.

## Implementing code from specs

The `*.bspec.json` files are the implementation target — read the behaviors and
invariants directly and implement them exactly. Review state does **not** gate
what you may read; it is the human reviewer's incremental-review ledger (which
units are new or changed since they last approved), not a filter on consumption.

New requirements: edit the Behavior Spec first, then implement — never encode a
new requirement in code without writing it into the spec.

## Prohibited actions

Never:
- record a review decision in `bspec.json` **except** when the human explicitly asked you
  to help review, and then only to approve or dispute `pending` units from a list they saw (or gave),
  as in *Assisting a large review* — otherwise only `bspec review` (a human keypress)
  writes decisions (project config — `lang`, `specGlobs`, the type-word `glossary` — is
  not a decision; maintaining it per *Source of truth* is fine);
- overwrite or drop any existing review record — you record (approve or dispute) only
  never-reviewed (`pending`) units, never overturn an existing
  `approved`/`rejected`/`disputed`/`stale` decision;
- agent-approve a unit that turns on business judgment, or touches deletion, money, auth,
  security/privacy, legal, external side effects, or anything irreversible — those stay the
  human's even when clearly worded (you may `dispute` one to surface a concern — that
  approves nothing — but never approve it);
- fabricate a semantic hash — always copy the live `units[key].hash` from `bspec status --json`;
- hide validation errors;
- silently replace an approved behavior;
- encode an implementation choice as observable product behavior;
- treat current source code as intended behavior without human review.
