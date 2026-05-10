# Cascade — structured pipeline

Cascade is an orchestration with a fixed sequence of phases and gate verdicts between them. Used when you need formal quality gates (the review phase must approve the design before implementation begins).

## Contents

- [Conceptual model](#conceptual-model)
- [Default stages](#default-stages)
- [Gate verdict](#gate-verdict)
- [Iteration counter](#iteration-counter)
- [Artifacts with dedup](#artifacts-with-dedup)
- [UI state in Wave 3.9](#ui-state-in-wave-39)
- [When cascade is useful](#when-cascade-is-useful)

## Conceptual model

A regular Roman run — free-form goal, Roman decides how to decompose. Cascade is the same, but:
1. **Stages** (phases) are predefined: contract, design, implementation, review, qa.
2. Between stages there is a **gate** (a judge agent) that evaluates the phase's output and decides: approve, return-to-stage (repeat), reject.
3. On return-to-stage the `iteration` counter increments for that phase.
4. Each stage may have multiple nodes (one stage = one or more agent runs).

```
contract --[gate]--> design --[gate]--> implementation --[gate]--> review --[gate]--> qa
              |                |                  |                  |
            return           return             return             return
              |                |                  |                  |
              v                v                  v                  v
          new iter         new iter          new iter            new iter
```

If the gate returns `approve` — move on. If `return-to-stage` — the current stage runs again with feedback from the gate. If `reject` — the run completes failed.

## Default stages

The code defines 5 phases (stages):

1. **contract** — requirements formalisation. The agent reads the goal, the input artifacts, and writes a formal contract: what should be produced, which constraints apply, which acceptance criteria.
2. **design** — the technical solution. The agent reads the contract and proposes architecture, technology choices, module breakdown.
3. **implementation** — the actual code. One or more agents code per the design.
4. **review** — code review. An agent (vera/svetlana/silent-failure-hunter) reviews the implementation, looks for problems.
5. **qa** — final check. Run tests, validate acceptance criteria, smoke tests.

Stage names and counts are configurable (via project settings or harness adapter), but the default is these 5.

## Gate verdict

A gate is a separate agent that runs **between** stages. It reads:
- The previous stage's artifacts (what the previous agent produced).
- Acceptance criteria (from the contract).
- The whole run's goal/context.

And returns a structured JSON:
```
{
  "verdict": "approve" | "return-to-stage" | "reject",
  "stage_name": "design",
  "comment": "Spec block is incomplete: does not cover edge case X",
  "items": [...]  // list of specific issues for return/reject
}
```

DC parses this JSON and decides:
- `approve` → next stage.
- `return-to-stage` → current stage runs again with iteration+1, the `gate_comment` is passed in.
- `reject` → run is marked failed.

The gate agent is configured per-stage via the harness adapter. Names usually look like `gate-design`, `gate-implementation`.

## Iteration counter

Each stage has `iteration` (default 1). If the gate says `return-to-stage` — iteration becomes 2, then 3, and so on.

There is a `max_iterations` (default 3). If you hit the cap and the gate still hasn't approved — the run is automatically marked failed with reason "max iterations reached at stage X".

In the DB:
- `orchestrator_nodes.iteration` — per node.
- `orchestrator_runs.current_stage` — where the run is right now.

## Artifacts with dedup

Each phase can write **artifacts** — structured results (e.g. the set of "rules" review found, the set of tasks design proposed).

An artifact is identified by `rule_id` or a similar key. Dedup: if iteration 1 already had `rule:auth-session-leak` and iteration 2 review found the same one again — DC does not duplicate, it marks it as found again.

This is needed so that:
- The "issues" list does not blow up across iterations.
- You can track how many times a rule kept resurfacing.

Artifacts are stored in the `cascade_artifacts` table.

## UI state in Wave 3.9

**Important:** in the current version (Wave 3.9) there is **no separate cascade page in the UI**. Cascade runs show up in the regular `/p/{slug}/orchestration` list alongside ordinary Roman runs. You can tell them apart only by data:
- A cascade run has the flag `kind=cascade` in `metadata` (or a similar field).
- The nodes have more hierarchy: stages + sub-nodes per stage.
- In messages — gate verdicts appear with a special `kind=gate_verdict`.

Visualisation of stages with progress, artifacts, iteration counters — TODO for future waves.

What **does exist** in the UI today:
- On `/p/{slug}/cascade-costs` — list of runs with total cost, includes cascade runs (if any).
- On `/p/{slug}/orchestration/{id}` — the regular list view of nodes/messages, you can manually trace the order via timestamps.

## When cascade is useful

- **Complex features with clear acceptance criteria** — where you need a `Spec` artifact for everyone to be on the same page.
- **High-stakes changes** — security review, payment-flow refactor — where you need a formal review-gate.
- **Agent teams with role separation** — someone designs, someone implements, someone reviews.
- **When repeatability matters** — a repeatable flow for typical tasks.

When **not** useful:
- Small tasks (5-stage overhead is not justified).
- Research / exploration (no clear acceptance criteria).
- Quick fixes (just start a regular Roman).

Cascade runs are more expensive than regular runs (more LLM calls, more tokens). Use it proportional to the scope.

---

See also:
- [`orchestration.md`](orchestration.md) — regular Roman runs.
- [`analytics-extras.md`](analytics-extras.md) — Cascade Costs analytics.
- Technical: [`../../features/cascade.md`](../../features/cascade.md), [`../../schema.md#cascade_artifacts`](../../schema.md), [`../../api.md`](../../api.md).
