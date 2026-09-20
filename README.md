<img src="docs/banner.svg" alt="Jev Ultrafast · Browser Use × TypeSafe" width="100%" />

# Jev Ultrafast ⚡ — Shinaru Reflex Runtime

**A System One reflex layer that chooses instead of generating.** It began as a browser agent with a dynamic, indexed action space; this fork grows it into the reflex plane for the Beowulf/COMPSD network, with Kimi Code as the fast generative worker.

```text
JEV judges.  Kimi thinks and produces.  Cursor experiments and builds.  Pepper interacts with the computer.
Beowulf routes and reconciles.  The relay communicates.  COMPSD records.  Verification proves.  You authorize.
```

The original browser demo below is unchanged and stays the regression fixture. The reflex runtime around it is described in [Reflex runtime](#reflex-runtime), [docs/architecture.md](docs/architecture.md), [docs/questions.md](docs/questions.md), and [docs/governance.md](docs/governance.md).

## The browser reflex

Give it one goal. [TypeSafe's Jev](https://docs.typesafe.ai/introduction) picks an operation and an element. A small LLM writes text only when the operation is `TYPE_TEXT`.

**Zürich → London on Google Flights in 7.1 seconds.** One natural-language goal, actual text generation, and loading waits included.

<a href="docs/demo.mp4"><img src="docs/demo.gif" alt="A real Google Flights search at 1× speed, with generated city names and dynamic operation/target decisions" width="100%" /></a>

[Watch the MP4](docs/demo.mp4) · [Measurements](docs/performance.md) · [Read the loop](jev_ultrafast/agent.py)

## The action space

Every observation produces a new element table:

```text
[1] button    Change ticket type · Round trip
[2] combobox  Where from?        · San Francisco
[3] combobox  Where to?          · empty
[4] textbox   Departure          · empty
...
```

The operations are `CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL_UP`, `SCROLL_DOWN`, `WAIT`, `DONE`, and `BLOCKED`. Only supported operations and targets are offered.

```text
                      one TypeSafe request
                     ┌───────────────────────────┐
page → element table → operation                 │
                     │ click_target              │
                     │ type_text_target          │
                     │ select_target, if present │
                     └─────────────┬─────────────┘
                         use the matching target
                                   │
                    CLICK [7] ─────┤──→ browser
                TYPE_TEXT [3] ─────┘
                          ↓
                   small LLM → text → browser
```

Target questions are speculative. If the operation is `CLICK`, only `click_target` can execute. Two decisions, **one network round trip**. Each target head contains only compatible elements. Native dropdown choices carry an observed element/option index.

There are no site-specific action scripts or prepared field strings in the policy. The Flights example supplies a goal and independently verifies the outcome. The screenshot renderer adds labels afterward; it does not drive the browser.

## Try it

```bash
git clone https://github.com/browser-use/jev-ultrafast.git
cd jev-ultrafast
uv sync
cp .env.example .env
# Add TYPESAFE_API_KEY and TEXT_MODEL_API_KEY.
uv run jev
```

Open **http://127.0.0.1:8766** and click **Start demo → Run automatically**. The inspector shows numbered elements, operation probabilities, target probabilities, and executed actions. **Choose next** pauses before execution.

Chrome connects through [Browser Harness](https://github.com/browser-use/browser-harness), installed by `uv sync`. Run `uv run browser-harness --doctor` if it needs connecting. Allow remote debugging in Chrome when prompted.

`TEXT_MODEL_API_KEY` is an OpenRouter key in the example configuration. The current demo uses `inception/mercury-2.5` with reasoning disabled. Gemini, GLM, and DeepSeek can also use the OpenAI-compatible text helper; configure the appropriate model, endpoint, and reasoning setting.

## Use the library

```python
from jev_ultrafast import Agent

with Agent(
    "https://www.google.com/travel/flights?hl=en",
    "Find one-way flights from Zurich to London on September 20, 2026, "
    "for one adult in economy. Stop when matching flight options are visible.",
) as agent:
    for state in agent.run():
        print(state["elapsed_ms"], state["status"])
```

Run with `uv run --env-file .env python your_script.py`. The same policy can run a different task:

```bash
uv run --env-file .env python examples/run.py \
  --url https://en.wikipedia.org/wiki/Main_Page \
  --goal 'Find and open the Wikipedia article about Gödel’s incompleteness theorems.'
```

`uv run --env-file .env python examples/flights.py --keep-open` performs the flight search, checks the actual route/date/results, and saves its trace. It does not select or book a flight.

## Why it moves

- **One request per decision cycle.** Operation and target heads share the same observed state.
- **No screenshots in the default agent loop.** Jev consumes structured state. The inspector opts into screenshots; the video uses a separate continuous screencast.
- **One browser call per snapshot.** Read visible controls, their names, values, and text atomically. Keep references to the actual DOM nodes.
- **Validate the selected target.** Clicks check the document, form values, target, and nearby context. Animation alone does not force another prediction. Resolve current geometry and reject covered controls before input.
- **Wait for useful state.** After typing into a combobox, wait for visible suggestions, capped at 200 ms. Other interactions get at most two animation frames or 50 ms. These reads happen after execution is logged.
- **Keep hidden tabs rendering.** Focus emulation prevents background animation throttling without switching Chrome's visible tab.
- **Send visible text.** Offscreen article bodies and footers do not fill the model context.
- **Reuse an interrupted text request.** A generated value survives a stale-page retry only if the entire text-helper input is unchanged.

Every executed target is resolved from an observed node. The executor rechecks page freshness and click occlusion. Model output never becomes selectors, coordinates, shell commands, or executable JavaScript. Text-helper output must parse as a small JSON object before typing.

## Reflex runtime

The browser loop asks two things in one request: *which operation?* and *which compatible element?* Every other domain here keeps that shape. Observed candidates get indices, Jev chooses among indices, code maps the index back to the observed thing. The model never emits selectors, coordinates, message bodies, shell commands, or `DONE` with authority.

```text
                     Beowulf / Pepper / Kimi / COMPSD
                                   │
                                   ▼
                     POST /decision  { domain, input, policy_context }
                                   │
   ┌───────────────────────────────┼────────────────────────────────┐
   │ action_spaces   observe → indexed candidates → typed questions │
   │ providers       TypeSafe today; the contract is ours           │
   │ core            validate → Recommendation → consume-once ledger│
   │ policy          HUMAN_REQUIRED first, then calibration locks   │
   │ evidence        receipts · traces · replay                     │
   └───────────────────────────────┼────────────────────────────────┘
                                   ▼
        { recommendation, answers, distributions, confidence,
          model_version, latency_ms, policy.verdict, decision_id, state_hash }
```

**Action spaces.** `BrowserActionSpace` wraps the original request byte-for-byte. `RelayActionSpace` picks `REPLY / ACK / FORWARD / ESCALATE / PARK / IGNORE` plus an observed message; it never sends. `AgentRoutingActionSpace` classifies a task packet and recommends the first executor from the ones actually offered. `RepoActionSpace` screens a change set and names the file most worth a reviewer's attention. `ComputerActionSpace` normalizes Pepper's observed screen elements into `CLICK / TYPE / WAIT / REQUEST_HELP / DONE / BLOCKED` with code-owned geometry.

**Consume once.** A decision is bound to the hash of the exact state it evaluated. `consume(decision_id, state, requested_action)` fails if the state changed or the decision was already used, and it happens before any side effect. Results are recorded against the consumed decision, so a lost observation cannot erase an execution. `evidence.replay_ledger` checks those invariants offline over the JSONL log.

**Authority.** `policy.rules` returns `human_required` for delete, deploy, money, credential, and release before reading a single probability. Every other gate compares against a threshold from a checked-in calibration lock for that exact question ID and model version. There is no global `confidence > 0.85`; a question without a calibrated lock resolves to `review`. All shipped locks are currently `uncalibrated`, so the default policy holds everything for review until a live labeled run produces real records.

**Kimi Code over ACP.** `adapters.kimi_acp` drives `kimi acp` as a JSON-RPC subprocess: `initialize`, `session/new`, `session/prompt`, streamed `session/update`, and `session/request_permission`, which is answered from a deterministic per-worker policy. `explore` and `plan` jobs are refused edit/execute tools; `coder` is refused anything matching a human-required command pattern. Kimi hooks are fail-open by Moonshot's documentation, so the hook entry point (`python -m jev_ultrafast.adapters.kimi_acp`) only writes receipts and advisory denials.

**Pepper.** `adapters.pepper.PepperLoop.step` observes, asks the gateway, and executes exactly one approved operation through a callback you supply. A `TYPE` recommendation returns `wake_kimi` with the field and state hash; no text is produced here. `DONE` returns `claimed_done`, which is a claim, not completion.

**Evidence.** Receipts come in four kinds (`file`, `transport`, `ack`, `proof`); `verify_chain` rejects a proof issued by the claimant. `TraceWriter` annotates decisions and verdicts onto OTel-shaped spans. `CompsdRecorder` refuses to record a relay ID twice.

```bash
uv run jev-gateway                 # loopback POST /decision, /consume, /result; prints the local token
uv run jev-eval                    # dry run of the labeled fixtures with the label oracle (free, offline)
uv run jev-eval --provider typesafe --record artifacts/eval-replay.jsonl --write-locks   # paid; writes real locks
uv run --env-file .env python examples/gateway_client.py   # ask the running gateway to route a task
```

`jev-eval --provider typesafe` is the only path that can mark a question `calibrated`, and only with at least 20 labels and a Brier score better than chance. The current fixture sets are smaller than that; they exercise the pipeline and give the first labels.

## Small enough to read

| File | Job |
| --- | --- |
| [agent.py](jev_ultrafast/agent.py) | The complete browser loop and text-helper handoff |
| [snapshot.js](jev_ultrafast/snapshot.js) | Atomic DOM snapshot, indexed controls, freshness guards |
| [browser.py](jev_ultrafast/browser.py) | Browser connection, current geometry, execution |
| [model.py](jev_ultrafast/model.py) | Dynamic operation/target heads and text generation |
| [questions.py](jev_ultrafast/questions.py) | Browser model instructions |
| [demo.py](jev_ultrafast/demo.py) | Local inspector |
| [core/](jev_ultrafast/core) | Versioned questions, typed validation, consume-once ledger, calibration records |
| [action_spaces/](jev_ultrafast/action_spaces) | Browser, relay, agent routing, repository, computer |
| [policy/](jev_ultrafast/policy) | Human-required categories, gates, calibration locks |
| [adapters/](jev_ultrafast/adapters) | Beowulf gateway, COMPSD receipts, Kimi ACP, Pepper loop |
| [evidence/](jev_ultrafast/evidence) | Receipts, traces, replay |
| [evals/](jev_ultrafast/evals) | Labeled fixtures and the calibration runner |

## Evidence and limits

The current video is a **7,073 ms** Google Flights run. Timing starts after initial page observation and includes model calls, generated text, browser work, stale decisions, and loading waits. A fresh independent check verifies the one-way setting, Zürich, London, September 20, 2026, and visible flight options. The video plays at 1×, with no opening hold and a 0.5-second final hold.

In six alternating runs with identical models and settings, both versions passed **3/3**. Median task time went from **9.450 s → 7.092 s**, a **25% reduction**; median browser protocol calls went from **1,092 → 101**. This is three repeats of one task on one browser profile, not a general reliability benchmark.

The same policy opened the requested Wikipedia article in **2.798 s** and passed a local hotel search/filter task in **1.896 s**. Runs, failures, source hashes, and measurement boundaries are in [performance.md](docs/performance.md).

A `DONE` choice still requires independent outcome verification. The DOM reader handles common HTML and ARIA controls, not the full accessible-name specification. Shadow roots, frames, canvas, uploads, pop-up tabs, nested scrolling, and arbitrary keyboard widgets remain outside this MVP. Owned tabs share the existing Chrome profile.

## Development

```bash
uv run ruff check .
uv run pytest
node --check jev_ultrafast/static/app.js
node --check jev_ultrafast/snapshot.js
uv build
```

Tests are offline, including the Kimi ACP client, which is exercised against a fake stdio agent. `uv run python scripts/check_guards.py` checks real controls in a local browser without model calls. Live examples, `jev-eval --provider typesafe`, and recording scripts make paid API calls. `scripts/record_flights.py <new-folder>` captures original browser timestamps; `scripts/render_demo.py <recording-folder>` renders that verified run at 1× and crops out the Google account strip. Credentials and raw traces stay ignored.

---

[Browser Use](https://github.com/browser-use/browser-use) · [Browser Harness](https://github.com/browser-use/browser-harness) · [TypeSafe speculative fan-out](https://docs.typesafe.ai/patterns/fan-out)
