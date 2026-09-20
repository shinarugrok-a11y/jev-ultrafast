# Shinaru Reflex Runtime

Jev Ultrafast started as a browser agent that chooses instead of generating. This fork keeps that loop intact as a regression fixture and generalizes its primitives into the System One reflex layer for the Beowulf/COMPSD network. Kimi Code is the fast generative worker; Cursor is the implementation lab; General Pepper Tusk is the pair of hands and eyes; Beowulf dispatches; the relay is the nervous system.

```text
                         HUMAN / HEXTURTLE
                               │
                               ▼
                    CHAT RELAY / COMPSD BUS
             identity • reply_to • receipts • evidence
                               │
                               ▼
                        ┌─────────────┐
                        │   BEOWULF   │
                        │ ORCHESTRATOR│
                        └──────┬──────┘
                               │
                  normalize + deterministic policy
                               │
                    ┌──────────▼──────────┐
                    │  JEV REFLEX PLANE   │   jev_ultrafast.core / action_spaces / providers
                    │    System One       │
                    │ classify · rank     │
                    │ score · wake?       │
                    │ route · risk        │
                    │ confidence          │
                    └──────────┬──────────┘
                               │ recommendations only
                     deterministic policy            jev_ultrafast.policy
                               │
       ┌───────────────────────┼───────────────────────┐
       ▼                       ▼                       ▼
   KIMI CODE              CURSOR LAB           GENERAL PEPPER TUSK
   explore/plan/coder     free-reign fork      VM / GUI / browser
   adapters.kimi_acp                           adapters.pepper
       └───────────────────────┼───────────────────────┘
                               ▼
                      artifacts + receipts            jev_ultrafast.evidence
                               │
                     independent verification
                               │
                     Beowulf relay handback            adapters.compsd
                               │
                         HUMAN APPROVAL
```

## What the browser agent already had

One observation snapshot. Parallel speculative decision heads in one request. Operation and compatible-target separation. Page fingerprints that invalidate stale decisions. Consume-once decisions so a retry cannot double-click. Action and model-call budgets. Probability and confidence logging. Independent `DONE` verification. Each of those becomes a general rule below.

## The universal ActionSpace

`action_spaces.base.ActionSpace` has three methods: `state()` (what the model sees), `questions()` (request key to `core.Question`), and `resolve(answers)` (validated answers to a `Recommendation` bound to observed candidates). Speculative heads are declared with `speculative_heads()`; `validate()` skips them and `resolve()` validates the single head matching the chosen operation with `use_head()`. `evaluate_space(space, provider, ledger)` performs one provider request, validation, resolution, and a ledger entry.

| Domain | Candidates | Operation head | Target head(s) | Also asks |
| --- | --- | --- | --- | --- |
| browser | DOM controls | `browser.operation.v1` | `browser.<op>_target.v1` | (original request, unchanged) |
| relay | messages in a thread | `relay.next_operation.v1` | `relay.reply_target.v1` for REPLY/ACK | needs_reply, likely_duplicate, human_review |
| agent_router | executors offered by the caller | `routing.best_executor.v2` | none | task class, three scores, nine nouls, should_wake |
| repository | changed files | `repo.change_risk.v2` (score) | `repo.riskiest_file.v1` | matches_request, tests_cover, human_review |
| computer | screen elements with geometry | `computer.operation.v1` | `computer.click_target.v1`, `computer.type_target.v1` | requires_generation, human_review |
| questions | none | none | none | any standard question IDs against an arbitrary state |

A `Recommendation` carries `operation`, `target`, `candidate` (the observed thing, including code-owned geometry or IDs), `confidence`, `probabilities`, `flags` (noul values by question ID), `scores`, and `authority = "recommendation"`. Nothing in it is executable.

## Providers

`providers.SystemOneProvider` is the contract: `evaluate(state, questions) -> Evaluation(answers, model_version, latency_ms, usage)`. `TypeSafeProvider` is TypeSafe's hosted Jev. `StubProvider` and `ReplayProvider` are offline. A later Laya/OpenJEV/local classifier sits behind the same contract without changing COMPSD.

## Consume once, against one state

`core.DecisionLedger` issues a `Decision` with `decision_id`, `state_hash`, `question_ids`, `answers`, `model_version`, `latency_ms`, and later `consumed_at`, `requested_action`, `result_receipt`. `consume()` raises `StaleDecision` if the current state hashes differently and `AlreadyConsumed` on a second use, and it runs before any side effect. `record_result()` requires a consumed decision. The optional JSONL log is replayable with `evidence.replay_ledger`, which reports double consumption, state drift, results without consumption, and duplicate results.

This is the browser agent's anti-double-action rule applied to the relay's duplicate-send problem: a decision to reply is usable once against the exact thread state it saw. If a new message arrived, re-evaluate.

## Authority

`policy.rules.Policy.evaluate(recommendation, categories, model_version)` applies, in order:

1. Any category in `HUMAN_REQUIRED` (`delete`, `deploy`, `money`, `credential`, `release`) returns `human_required` before any probability is read. Categories come from application code: the relay's packet classification, `forbidden_changes()` over protected repository paths, or `categories_for_command()` over a shell command.
2. Each gate in `policy/thresholds/gates.json` names a question ID, a direction, and a verdict. The numeric threshold comes only from `policy/calibration_locks/<question_id>.json`. A missing or `uncalibrated` lock, or a lock for a different model version, resolves to `review`.
3. A confidence floor for the operation head, again from its lock.

`task.human_review_recommended.v4` exists because a careful operator's instinct is a useful signal. `human_approval_required` does not exist as a question because whether approval is required is not the model's to decide.

## Calibration

`evals/<suite>/fixtures.jsonl` holds gateway requests plus labels keyed by question ID. `jev-eval` runs them through a provider, computes accuracy and multi-class Brier for choices, Brier and the best threshold for nouls, and mean absolute error for scores, then writes one record per question ID. A record is `calibrated` only from a live or replayed provider with at least `MIN_FIXTURES` (20) labels and a Brier score better than chance. The label oracle proves the pipeline and refreshes fixture counts; it can never write a calibrated record. `tests/test_evals.py` fails if the checked-in locks disagree with the fixtures.

## Kimi Code

`kimi acp` is JSON-RPC over stdio. `adapters.kimi_acp.KimiACP` sends `initialize` (advertising no fs or terminal capabilities, so Kimi runs those itself), `session/new`, `session/prompt`, and `session/cancel`; collects `session/update` notifications; and answers `session/request_permission` from `WorkerPolicy`. Jobs map to Kimi's built-in sub-agents: `explore` (read-only reconnaissance), `plan` (no shell, no edits), `coder` (bounded implementation). The prompt asks for the sub-agent; the permission policy enforces the boundary, refusing tool kinds outside the worker's allowlist and any command matching a human-required pattern.

Hooks (`SessionStart`, `PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop`, `Stop`, ...) are fail-open: an erroring or timed-out hook allows the operation. So `hook_main()` only appends a receipt to `JEV_RECEIPTS` and, for `PreToolUse` on a human-required command, prints an advisory `permissionDecision: deny`. The thing capable of saying no is the permission answer plus COMPSD/OpenShell.

## Pepper

```text
Pepper observes screen/state
          ↓
normalize_screen builds legal actions with code-owned geometry
          ↓
Jev: CLICK? TYPE? WAIT? REQUEST_HELP? DONE? BLOCKED?  (+ which element)
          ↓
Beowulf policy: act / review / park / human_required
          ↓
Pepper consumes the decision, then executes exactly one approved operation
          ↓
state receipt recorded against the decision, then re-observe
```

`TYPE` returns `wake_kimi` with the field and the state hash so the generation step can be checked against the same state. `DONE` returns `claimed_done`. Nothing in this loop closes a task.

## Completion

Jev can answer `completion.claim_supported.v3`; it cannot set `DONE`. Completion needs the receipt chain: `file` (something was written), `transport` (it left us), `ack` (the other side confirmed), `proof` (the external outcome happened, issued by someone other than the claimant). `evidence.verify_chain` is deterministic. Beowulf validates the chain, the deterministic verifier checks tests, expected files, browser receipt, branch/commit, and forbidden changes, and the human gates whatever policy says needs a human.

## A concrete workflow

> "The Chrono Maps world selector is broken. Figure out the problem, fix it, and show me it works."

1. Relay receives the packet. Beowulf validates identity and rejects a repeated relay ID (`CompsdRecorder.seen`).
2. `POST /decision {domain: agent_router}` returns `task.class = debugging`, `requires_repository_write ≈ .98`, `requires_visual_verification ≈ .94`, `best_executor = kimi_explore`, `consequence = 2/5`. Policy: no human-required category; gates consulted against locks.
3. `Job("explore", ...)` runs over ACP. Its permission policy refuses edits and shell. The result is evidence, not a change.
4. Another routing decision on the new state: bounded patch, generation required. `Job("plan", ...)` or `Job("coder", ...)`.
5. The Cursor lab branch implements and iterates. Tests run.
6. Pepper opens the build; `PepperLoop.step` drives verification one operation at a time; a `proof` receipt is issued by Pepper, not by the coder.
7. `POST /decision {domain: questions, question_ids: [completion.claim_supported.v3]}` gives a probability. It does not close anything.
8. The deterministic verifier checks tests, files, browser receipt, branch, and `forbidden_changes`. Beowulf sends REPORT + RECEIPT + evidence references. A human approves merge or deploy where required.
