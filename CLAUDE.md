# CLAUDE.md — behavior-spec (bspec)

Deterministic, zero-LLM CLI for Behavior Specs (`*.bspec.json`). Normative spec:
`docs/spec-v1.md`. Agent workflow + full authoring rules:
`skills/behavior-spec/SKILL.md`.

## Writing spec text (`name` / `title` / `rationale` / `description`) — grounded, not ad-hoc

Four human fields, each a distinct role; established requirements-engineering
practice. Operational templates live in `skills/behavior-spec/SKILL.md`; this is
the grounding for why.

**name = a short human label** (required, every kind). Authored in the project
`lang` — the reviewer's handle when the `id` is cryptic. The tool prepends the raw
`[kind][direction]` tag at review time (e.g. `[behavior]`, `[event][input]`), so
**never write the tag into `name` yourself** and never translate it. Cosmetic
(not hashed).

**title = the requirement, in an EARS pattern** — EARS = Easy Approach to
Requirements Syntax (Mavin / Rolls-Royce). Use `must`, not `shall`. Required for
`behavior`/`invariant` (the actual rules); optional for `module`/`flow`. **Hashed**:
it is the prose a layperson approves, so editing it re-opens review.

| bspec kind | EARS pattern | title template |
|---|---|---|
| behavior (event) | event-driven | `When <event> [and <where>], the system must <result>.` |
| behavior + `given` | state + event | `While <given>, when <event>, the system must <result>.` |
| behavior `forbid` | unwanted behaviour | `If <event>, then the system must not <result>.` |
| invariant | ubiquitous / state-driven | `The system must always <X>.` / `While <state>, the system must <X>.` |
| module / flow | container (not a single requirement) | scope / ordered statement |

**rationale = the why** — INCOSE *Guide to Writing Requirements*: separate
rationale from the requirement; keep the requirement concise and put the
explanation in the rationale attribute. So `rationale` is *why it exists / what it
prevents* — never a paraphrase of the `title` or the CEL. Required + **hashed**.
Also from INCOSE GtWR: R2 active voice + named subject; singularity (one thought —
split when `and/or/then` joins two); define shared terms in `glossary` (R4/R39/R40).

**description = what a definition is** — `interface`/`event`/`observable` only;
optional; the channel/value semantics. Hashed *when the definition is referenced
by a reviewed rule* (its meaning shapes that approval).

**Each unit must be standalone-reviewable** — ISO/IEC/IEEE 29148 quality
characteristics (singular/atomic, complete, unambiguous, verifiable) + INVEST
*Independent*: a cold reviewer decides agree/reject from the one card alone,
without reading sibling units or the code.

Refs: [EARS](https://alistairmavin.com/ears/) · ISO/IEC/IEEE 29148 · [INCOSE GtWR](https://www.incose.org/docs/default-source/working-groups/requirements-wg/guidetowritingrequirements/incose_rwg_gtwr_v4_summary_sheet.pdf).
