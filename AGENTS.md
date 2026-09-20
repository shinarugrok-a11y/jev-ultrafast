# Jev Ultrafast — Shinaru Reflex Runtime

Read README.md, docs/architecture.md, and docs/governance.md before editing. Keep every loop small: state -> indexed candidates -> operation + target -> recommendation -> deterministic policy -> one execution -> receipt.

Browser reflex (regression fixture, keep it working):

- The input is one natural-language goal. Do not add site-specific plans or hardcoded field values.
- TypeSafe chooses an operation and operation-specific target heads in one request. Consume only the selected operation's target.
- TYPE_TEXT invokes the text LLM. Cache a stale retry's value only while its entire helper input is identical.
- Screenshots are optional; the model does not consume them. Keep demonstration footage at its original speed.

Reflex runtime:

- Every judgment has a versioned question ID (`domain.name.vN`). Change the wording, bump the version.
- Targets must map to observed candidates and supported operations. Never let the model emit selectors, coordinates, message bodies, shell commands, or executable code.
- A decision is consumed once, against the state hash it evaluated, before any side effect. Never retry a mutation. Log execution before observing its result.
- `delete`, `deploy`, `money`, `credential`, `release` are human-required in `policy/rules.py`. Jev does not get a vote. There is no `human_approval_required` question.
- Thresholds come only from `policy/calibration_locks/`. No global `confidence > x`. Uncalibrated resolves to `review`. Only `jev-eval --provider typesafe|replay` may write a calibrated lock.
- The gateway returns recommendations. It never sends relay messages, switches lanes, declares DONE, approves artifacts, or authorizes operations.
- Kimi is driven over ACP (`kimi acp`), never by scraping a TUI. Hooks are fail-open: receipts and advisory denials only.
- Verify actual final outcomes independently. A DONE choice or a `claim_supported` probability is not proof. Proof receipts must not be issued by the claimant.
- Keep credentials server-side and .env ignored. Tests must not call paid APIs.
- Keep examples, README claims, raw evidence, fixture counts, calibration locks, and model-call counts consistent. Run `uv run jev-eval --write-locks` after changing fixtures.
- Do not commit or push unless the user requests it.

Checks: uv run ruff check ., uv run pytest, node --check jev_ultrafast/static/app.js, node --check jev_ultrafast/snapshot.js, uv build.
