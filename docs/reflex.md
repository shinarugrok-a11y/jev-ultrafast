# Shinaru reflex runtime

Jev Ultrafast is still a working browser agent. This fork also hosts the **System One reflex plane** for Beowulf/COMPSD.

```text
HUMAN / HEXTURTLE
        │
        ▼
CHAT RELAY / COMPSD BUS
        │
        ▼
     BEOWULF
        │
        ▼
  JEV REFLEX PLANE     ← recommendations only
        │
        ├── Kimi Code (explore / plan / coder over ACP)
        ├── Cursor lab (this fork)
        └── Pepper (hands / eyes)
```

## Separation of powers

| Layer | May | Must not |
| --- | --- | --- |
| Jev | Classify, rank, score, recommend a wake/route | Send/resend relay mail, switch lanes, declare DONE, approve artifacts, authorize operations |
| Kimi Code | Plan, explore, generate text/code in isolated workers | Be the security barrier (hooks fail open) |
| Cursor | Rewrite this lab | Hold production secrets or push to the approved branch |
| Pepper | Execute one approved computer/browser operation | Invent TYPE_TEXT strings or skip consume-once |
| Beowulf | Route, consume-once, attach receipts, verify | Treat Jev confidence as a global cutoff |
| Human | Delete, deploy, money, credential use, release | — |

`human_review_recommended` is a Jev noul. Whether approval is **required** is deterministic policy.

## Gateway

Beowulf owns one local process:

```bash
uv run jev-gateway
# POST http://127.0.0.1:8767/decision
```

The TypeSafe key stays in the gateway environment. Callers send `state`, `questions` or a `policy_context.domain`, and get `answers`, distributions, confidence, `decision_id`, and `state_hash`. A decision is usable once against exactly that hash.

## Calibration

Every important question has a checked-in lock under `jev_ultrafast/policy/calibration_locks/`. Thresholds are per question id, model version, and policy version. There is no `confidence > .85` rule.

## Browser demo

The original loop in `agent.py` remains the regression fixture. Independent outcome checks still beat a `DONE` choice. The reflex plane uses `completion.claim_supported.v3` the same way: Jev may say the claim looks supported; receipts close the task.
