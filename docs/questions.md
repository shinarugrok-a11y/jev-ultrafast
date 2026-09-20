# Standard questions

Every judgment has an ID of the form `domain.name.vN`. A wording change bumps the version; a stored threshold for `v1` never applies to `v2`. Definitions live in `jev_ultrafast/core/questions.py` and the domain modules under `action_spaces/`. Calibration status per ID is in `jev_ultrafast/policy/calibration_locks/`; at the time of writing every lock is `uncalibrated` because no live labeled run has been recorded yet.

## Routing and task shape

| ID | Type | Levels / options |
| --- | --- | --- |
| `routing.best_executor.v2` | Choice | deterministic, kimi_explore, kimi_plan, kimi_coder, cursor, pepper, grok, codex, human, park (narrowed to what the caller offers) |
| `task.class.v1` | Choice | information, research, planning, coding, debugging, browser, computer_use, relay, verification, unknown |
| `task.complexity.v1` | Score | 0 trivial … 5 many coupled unknowns |
| `task.consequence.v1` | Score | 0 harmless … 5 irreversible loss, money, or credentials |
| `task.context_need.v1` | Score | 0 self-contained … 5 deep specific prior context |
| `task.requires_generation.v1` | Noul | new text or code must be composed |
| `task.requires_browser.v1` | Noul | a web page must be operated |
| `task.requires_repository_write.v1` | Noul | repository files must change |
| `task.requires_existing_context.v1` | Noul | depends on context not in the state |
| `task.requires_visual_verification.v1` | Noul | proof needs a screen or rendered output |
| `task.likely_duplicate_work.v1` | Noul | already done, in progress, or a repeat |
| `task.human_review_recommended.v4` | Noul | a careful operator would want a look (recommendation, not requirement) |

## Waking, completion, relay, repository

| ID | Type | Notes |
| --- | --- | --- |
| `agent.should_wake.v1` | Noul | waking the named sleeping agent adds value now |
| `completion.claim_supported.v3` | Noul | evidence supports the claim independent of the claim itself |
| `relay.needs_reply.v1` | Noul | the newest message expects a reply from us |
| `relay.next_operation.v1` | Choice | REPLY, ACK, FORWARD, ESCALATE, PARK, IGNORE |
| `relay.reply_target.v1` | Choice | observed message indices; consumed only for REPLY/ACK |
| `repo.change_risk.v2` | Score | 0 cosmetic … 5 auth, data, deployment, or money paths |
| `repo.riskiest_file.v1` | Choice | observed changed-file indices |
| `repo.change_matches_request.v1` | Noul | the change does what was asked, nothing else |
| `repo.tests_cover_change.v1` | Noul | included or reported tests exercise the change |

## Browser and computer

| ID | Type | Notes |
| --- | --- | --- |
| `browser.operation.v1` | Choice | CLICK, TYPE_TEXT, SELECT, SCROLL_UP, SCROLL_DOWN, WAIT, DONE, BLOCKED as offered by the page |
| `browser.click_target.v1`, `browser.type_text_target.v1`, `browser.select_target.v1` | Choice | observed element indices; only the head matching the operation is consumed |
| `computer.operation.v1` | Choice | CLICK, TYPE, WAIT, REQUEST_HELP, DONE, BLOCKED as offered by the screen |
| `computer.click_target.v1`, `computer.type_target.v1` | Choice | observed element indices with code-owned geometry |

## What is deliberately not a question

`human_approval_required`. Whether approval is required belongs to deterministic policy:

```text
delete          → HUMAN REQUIRED
deploy          → HUMAN REQUIRED
money           → HUMAN REQUIRED
credential use  → HUMAN REQUIRED
release         → HUMAN REQUIRED

JEV does not get a vote.
```

## Gates

`jev_ultrafast/policy/thresholds/gates.json` lists which probabilities gate behavior and what tripping does (`review` or `park`), optionally scoped to operations (for example `relay.needs_reply.v1` only matters when the recommendation is `REPLY`). The numeric threshold is never in that file; it comes from the calibration lock for the question ID and model version, or the gate resolves to `review`.
