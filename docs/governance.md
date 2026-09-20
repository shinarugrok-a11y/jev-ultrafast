# Governance of the lab fork

This repository is public. The `cursor/free-reign-*` branches are a lab: Cursor may rewrite architecture, add dependencies, benchmarks, adapters, tests, docs, and experiments there. The lab has free rein over code and none over authority.

## What the lab never receives

- Relay credentials, production VM credentials, COMPSD secrets, or TypeSafe keys. `.env` stays ignored; `.env.example` holds names only.
- Permission to push into the approved branch or deployment. Work lands through a pull request that a human merges.
- A vote on `delete`, `deploy`, `money`, `credential`, or `release`. Those categories are `human_required` in `policy/rules.py` regardless of any probability, and a change to that list is itself a human decision.

## What the runtime never does

- Send, resend, acknowledge, or forward a relay message. `RelayActionSpace` recommends; relay code decides and records.
- Switch lanes, declare `DONE`, approve an artifact, or authorize an operation. Every response carries `authority: "recommendation"`.
- Emit selectors, coordinates, shell commands, message bodies, or code from the model. Targets are indices into observed candidates; geometry and IDs are code-owned.
- Retry a browser or computer mutation. A decision is consumed before the side effect and its result is recorded before the next observation.
- Treat a hook as a security barrier. Kimi hooks are fail-open; the adapter's permission answers and COMPSD/OpenShell are the barrier.
- Use a threshold that is not in a calibration lock for that exact question ID and model version.

## What a change to this fork must keep consistent

- Examples, README claims, raw evidence, and model-call counts. The browser measurements in `docs/performance.md` are unchanged by the reflex runtime and must stay that way unless re-measured.
- Fixture counts and calibration locks. `tests/test_evals.py` fails when `policy/calibration_locks/` disagrees with `evals/*/fixtures.jsonl`; regenerate with `uv run jev-eval --write-locks` (dry run, counts only).
- A calibrated lock only from `jev-eval --provider typesafe` or `--provider replay`, with at least 20 labels and a Brier score better than chance. Do not hand-edit a lock to `calibrated`.
- Tests offline. Nothing under `tests/` may call a paid API.

## Where authority lives, in one line each

JEV judges. Kimi thinks and produces. Cursor experiments and builds. Pepper interacts with the computer. Beowulf routes and reconciles. The relay communicates. COMPSD records. Verification proves. You authorize.
