# Jev Ultrafast — Shinaru Reflex Runtime

Read README.md and docs/reflex.md before editing.

Browser demo: page -> indexed elements -> operation + target -> execution.

- The input is one natural-language goal. Do not add site-specific plans or hardcoded field values.
- TypeSafe chooses an operation and operation-specific target heads in one request. Consume only the selected operation's target.
- Targets must map to observed elements and supported operations. Never let the model emit selectors or executable code.
- TYPE_TEXT invokes the text LLM. Cache a stale retry's value only while its entire helper input is identical.
- Never retry a browser mutation. Log execution before observing its result.
- Screenshots are optional; the model does not consume them. Keep demonstration footage at its original speed.
- Keep credentials server-side and .env ignored. Tests must not call paid APIs.
- Verify actual final outcomes independently. A DONE choice is not proof of success.
- Keep examples, README claims, raw evidence, and model-call counts consistent.
- Do not commit or push unless the user requests it.

Reflex plane: Jev judges; Kimi produces; Cursor experiments; Pepper acts; Beowulf routes; humans authorize.

- Recommendations only. Jev must not send/resend relay mail, switch lanes, declare DONE, approve artifacts, or authorize operations.
- Consume a decision once, against the exact `state_hash` it evaluated. If state changed, re-evaluate.
- Thresholds live on named calibration locks. Never a global `confidence > .85`.
- `human_review_recommended` is a Jev noul. delete/deploy/money/credential use/release are HUMAN REQUIRED with no Jev vote.
- Drive Kimi Code through ACP JSON-RPC, not a TUI. Hooks emit receipts and fail open; they are not the security barrier.
- Cursor free-reign (`cursor/FREE_REIGN.md`) may change this lab. It must not receive production secrets or push to an approved branch.

Checks: uv run ruff check ., uv run pytest, node --check jev_ultrafast/static/app.js, uv build.
