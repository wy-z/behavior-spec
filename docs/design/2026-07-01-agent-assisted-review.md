# Agent-assisted review — design

Status: revised 2026-07-07 — Aspect 2 gains a **`disputed`** outcome: on delegation the agent
may flag a concern (with a mandatory reason) instead of approving, and the review card now
renders a record's `comment` (reversing the earlier no-comment-rendering non-goal). Revised
2026-07-04 — Aspect 2 records **human-delegated approval** directly in `bspec.json` (was: an
advisory `bspec-notes.json` sidecar). Aspect 1 unchanged.
Scope: how a coding agent helps with review **without** an LLM inside the deterministic
core, and without approving anything the human did not delegate.

## Constraints (non-negotiable)

- **The core stays zero-LLM.** `bspec` does no model work; any agent reasoning happens
  outside the CLI. Approvals live in `bspec.json` keyed by the unit's semantic hash, so any
  later change to the prose/CEL re-opens review regardless of who approved.
- **Approval is the human's to give or delegate.** By default only `bspec review` (a human
  keypress) writes review decisions into `bspec.json`. The agent writes an approval
  **only** when the human explicitly asks it to help review — then it acts as the human's
  delegate, never on its own initiative.
- **Clarity ≠ correctness.** An agent can judge *expression quality* (does the prose
  faithfully & unambiguously describe the CEL?) but not whether a well-expressed behavior
  *should exist*. A perfectly worded `delete account without confirmation` is high-clarity
  and still business-wrong. So the agent clears only expression-clear, mechanically-correct
  units and leaves every business/product judgment to the human.

## Two aspects

Review help splits into two points in the workflow, sharing one analysis (does the prose
faithfully and unambiguously describe the CEL?):

### Aspect 1 — spec self-review (before the human gate)

After `bspec validate` passes and before asking for human review, the agent reviews the
**semantic** layer the deterministic validator cannot check:

- prose↔CEL fidelity — does `title`/`rationale` faithfully & completely describe what the
  CEL/schema enforces?
- EARS-pattern conformance (by kind);
- singularity (one thought per unit — no hidden `and`/`or`);
- ambiguity (vague terms not pinned in `glossary`/CEL);
- standalone-reviewability (decidable from the one card);
- cross-unit conflict (overlapping `given`/`when` with contradictory `then`);
- `rationale` is the *why*, not a paraphrase of `title`/CEL.

Clear-cut issues → the agent edits the `*.bspec.json` and re-validates (on
`pending`/`disputed`/`stale` units; `approved` and `rejected` units are
**surfaced, not auto-fixed** — editing one silently re-opens or replaces a human
decision). Judgment calls → surfaced to the human. This gate approves nothing.

**Delivery: prompt-level only** (a mandatory checklist section in
`skills/behavior-spec/SKILL.md`, gate 2 of *Behavior generation*). prose↔CEL fidelity is a
semantic judgment; it cannot be a zero-LLM `validate` check, so it lives in the agent and
the validator boundary stays mechanical (types/refs/schema).

### Aspect 2 — volume triage by delegated approval

When many units are pending/stale and the human asks for help, the agent records approvals
for the pending units it can confidently clear, **disputes** — with a reason — the ones it
has a specific concern about, and leaves the rest. (A dispute is the sole raised-concern
state: the human's `[c]` review key records `disputed` too; there is no separate
`changes_requested`.) The rules:

- **Opt-in + a list the human saw.** Only when the human explicitly asks, over a scope they
  name (module / kind / id list — "all pending" or a bare "help me review" is not a seen
  list). Unless the human gave the exact ids, the agent shows the units it would approve
  and gets a go-ahead before any write — never any scope swept unseen.
- **`pending` only — never overturn a decision.** The agent records (approves or disputes)
  only units `bspec status --json` reports as `pending` (never reviewed). It never edits a
  unit already carrying `approved`/`rejected`/`disputed`/`stale`; overturning a human's call
  (or its history) is the human's job. This keeps direct editing from silently destroying a
  prior human decision.
- **Low-stakes only.** The Aspect-1 checks pass **and** the requirement is mechanical and
  self-evidently right. A hard exclusion list is never agent-approved even when perfectly
  worded: deletion/data-loss, money/billing, auth/permissions, security/privacy,
  legal/compliance, external side effects, anything irreversible/policy-laden. Clarity ≠
  correctness is the reason the line is drawn at *consequence*, not just wording.
- **Dispute instead of approve when you have a concern.** For a `pending` unit the agent
  cannot clear but has a *specific* concern about (a likely error, an ambiguity, a cross-unit
  contradiction, or a high-stakes consequence worth surfacing), it records
  `decision: "disputed"` with the concern as its `comment` (prefixed `agent-disputed:`)
  rather than leave it silently pending. Unlike approval, dispute is **not** low-stakes-gated
  — it approves nothing, so flagging a concern on a high-stakes unit is exactly its job; the
  human still decides.
- **Direct edit, no new code.** There is no non-interactive approve command; the agent adds
  an entry to the `reviews` map of `bspec.json` with the **live** `semanticHash` (copied from
  `bspec status --json`), `decision: "approved"`, `reviewedAt`, and a `comment`, then re-runs
  `bspec status --json` to confirm the unit reads `approved` and nothing else moved (a wrong
  hash → `stale`; malformed JSON → a crash).
- **Provenance in a `comment` prefix.** The record has no reviewer field and we add none (no
  schema change); every agent approval's `comment` must begin with the literal
  `agent-approved:`, a greppable marker distinguishing it from a human approval, followed by
  why the unit is clearly correct.
- **Hash-bound like any approval.** The approval is keyed to the current semantic hash, so a
  later change to the prose/CEL drifts it to `stale` and re-opens review — the agent's
  approval is exactly as durable (and as revocable) as a human's.

The human still owns the boundary: they choose to delegate, they get back a report of what
the agent approved (with reasons) and what it left, and they decide everything the agent
left. Every agent approval is visible and reasoned in `bspec.json`.

## Why this over the earlier designs

Two earlier options were considered and dropped:

- **Advisory sidecar (design "X").** The agent wrote expression-quality flags into a
  `bspec-notes.json` sidecar that `bspec review` rendered; the human still pressed every key.
  It kept the human gate absolute but did not actually reduce the human's *volume* — they
  still opened every card — and it added a module + render path + tests for advisory output.
  Dropped in favor of real delegation.
- **Auto-approve everything clear (unguarded "Y").** The agent approves any high-clarity
  unit with no human ask. Dropped: clarity ≠ correctness — it would approve well-worded but
  business-wrong behaviors with no human in the loop.

The shipped Aspect 2 is the guarded middle: the agent approves, but only on explicit
delegation, only expression-clear + mechanically-correct units, with a reasoned audit
comment, and always hash-bound so any drift re-opens it.

## Files

- `docs/design/2026-07-01-agent-assisted-review.md` — this doc.
- `skills/behavior-spec/SKILL.md` — Aspect 1 self-review gate; Aspect 2 delegated-approval
  protocol (opt-in, direct `reviews` edit with the live hash + audit comment); updated
  Prohibited actions.

The original delegated **approval** needed no product-logic change: the review record
already carried an optional `comment` (`review_state.schema.json`), not part of the semantic
hash, so recording a reason neither needed new code nor re-opened review. The **`disputed`**
outcome (2026-07-07) adds a little — a `decision` value reusing the stale/hash machinery, a
schema `if disputed then comment` rule, `disputed` in `bspec review`'s default filter, and
card rendering of the record's `comment` — and **removes** `changes_requested`, whose role
("a raised concern, with a reason") is now `disputed` (any legacy `changes_requested` record
downgrades to `stale`, the standard unsupported-decision path). All still zero-LLM and
hash-neutral (goldens unchanged).

## Non-goals (YAGNI — build only if the MVP shows the gap)

- No `bspec approve` command; the agent edits `bspec.json` directly and re-checks with
  `bspec status --json`.
- No reviewer-identity field in the schema; provenance rides in the `agent-approved:`
  comment prefix. A schema-enforced `reviewerType: human|agent` is the upgrade **only** if a
  future need is adversarial-proof provenance (a cooperative agent following the SKILL writes
  the prefix); not now.
- No agent write to `stale`/decided units (the human owns re-review of anything already
  touched). *(Rendering `comment` on the card was formerly a non-goal; the `disputed` status
  reverses it — a record's comment now shows as review metadata, distinct from spec prose.)*
