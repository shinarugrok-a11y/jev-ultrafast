"""Offline contracts for the Shinaru reflex plane. No paid APIs."""

import json
from pathlib import Path

import pytest

from jev_ultrafast.action_spaces import (
    AgentRoutingActionSpace,
    BrowserActionSpace,
    ComputerActionSpace,
    RelayActionSpace,
)
from jev_ultrafast.action_spaces.browser import index_actions
from jev_ultrafast.adapters import BeowulfOrchestrator, SystemOneGateway
from jev_ultrafast.adapters.compsd import Packet
from jev_ultrafast.adapters.kimi_hooks import handle
from jev_ultrafast.adapters.pepper import PepperLoop
from jev_ultrafast.core.calibration import CalibrationLock, apply_lock, brier_score, load_lock
from jev_ultrafast.core.catalog import COMPSD_QUESTIONS, question_set
from jev_ultrafast.core.decision import AlreadyConsumed, DecisionLedger, StaleDecision, state_hash
from jev_ultrafast.core.questions import as_wire, choice_question
from jev_ultrafast.core.tree import bind_hierarchy, hierarchical_choice
from jev_ultrafast.core.validation import validate_choice, validate_noul, validate_score
from jev_ultrafast.evidence.completion import verify_completion
from jev_ultrafast.evidence.receipts import FileReceipt, Receipt, redact
from jev_ultrafast.evidence.replay import replay_decision
from jev_ultrafast.policy.authority import approval_required
from jev_ultrafast.policy.routing import route_recommendation
from jev_ultrafast.providers.base import ScriptedProvider

LOCK_DIR = Path(__file__).resolve().parent.parent / "jev_ultrafast" / "policy" / "calibration_locks"


def choice(ids, selected, confidence=1.0):
    keys = list(ids)
    return {"choice": selected, "confidence": confidence, "probabilities": {i: float(i == selected) for i in keys}}


def score_answer(levels, value, confidence=1.0):
    idx = str(min(max(int(round(value)), 0), len(levels) - 1))
    return {
        "score": float(value),
        "legend": {str(i): levels[i] for i in range(len(levels))},
        "probabilities": {str(i): float(str(i) == idx) for i in range(len(levels))},
        "confidence": confidence,
    }


def noul(value):
    return {"noul": value}


def routing_script(executor="kimi_explore", task="debugging", wake=0.9, generation=0.95):
    questions = AgentRoutingActionSpace().questions({})

    def answers(_state, asked):
        out = {}
        for qid, question in asked.items():
            if question["type"] == "choice":
                if "executor" in qid:
                    selected = executor
                elif "task_class" in qid:
                    selected = task
                else:
                    selected = next(iter(question["criteria"]))
                if selected not in question["criteria"]:
                    selected = next(iter(question["criteria"]))
                out[qid] = choice(question["criteria"], selected)
            elif question["type"] == "score":
                out[qid] = score_answer(question["criteria"], 2)
            else:
                value = wake if "should_wake" in qid else generation if "generation" in qid else 0.2
                out[qid] = noul(value)
        assert set(out) == set(questions)
        return out

    return ScriptedProvider(answers)


def test_catalog_contains_the_standardized_questions():
    ids = set(COMPSD_QUESTIONS)
    assert "routing.best_executor.v2" in ids
    assert "task.human_review_recommended.v1" in ids
    assert "human_approval_required" not in ids
    assert question_set(["relay.needs_reply.v1"])["relay.needs_reply.v1"]["type"] == "noul"


def test_choice_validation_still_rejects_invented_options():
    with pytest.raises(ValueError, match="Invalid System One"):
        validate_choice(choice(["a", "b"], "a") | {"choice": "invented"}, {"a", "b"})


def test_noul_and_score_validation():
    validate_noul(noul(0.4))
    validate_score(score_answer(["low", "mid", "high"], 1), ["low", "mid", "high"])
    with pytest.raises(ValueError):
        validate_noul({"noul": 4})
    with pytest.raises(ValueError):
        validate_score({"score": 9, "probabilities": {"0": 1}, "confidence": 1}, ["a", "b"])


def test_browser_space_matches_legacy_index_and_ignores_unused_heads():
    actions = [
        {"id": "e1", "kind": "fill", "label": "Search", "role": "textbox", "value": "", "node": 10},
        {"id": "e2", "kind": "click", "label": "Open Search", "role": "textbox", "value": "", "node": 10},
        {"id": "e3", "kind": "click", "label": "Go", "role": "button", "value": "", "node": 20},
        {"id": "wait", "kind": "wait", "label": "Wait"},
    ]
    space = BrowserActionSpace()
    observed = space.observe({"actions": actions, "url": "https://example.test/", "title": "Search", "text": "Search"})
    elements, targets, controls = index_actions(actions)
    assert observed["elements"] == elements
    questions = space.questions(observed, goal="Find a book")
    assert set(questions) == {"operation", "click_target", "type_text_target"}
    bound = space.bind(
        {
            "operation": choice(questions["operation"]["criteria"], "CLICK"),
            "click_target": choice(questions["click_target"]["criteria"], "2"),
            "type_text_target": {"choice": "invented"},
        },
        observed,
    )
    assert bound["choice"] == "e3" and bound["operation"] == "CLICK" and bound["kind"] == "recommendation"


def test_relay_space_cannot_bind_a_send():
    space = RelayActionSpace()
    observed = space.observe({"packet": {"packet_id": "p1", "identity": "hexturtle", "text": "hi"}})
    questions = space.questions(observed)
    assert "send" not in questions["operation"]["criteria"]
    bound = space.bind(
        {
            "operation": choice(questions["operation"]["criteria"], "HOLD"),
            "relay.needs_reply.v1": noul(0.1),
            "task.likely_duplicate_work.v1": noul(0.2),
            "routing.best_executor.v2": choice(questions["routing.best_executor.v2"]["criteria"], "park"),
        },
        observed,
    )
    assert bound["operation"] == "HOLD"


def test_decision_is_usable_once_against_exact_state():
    ledger = DecisionLedger()
    state = {"packet_id": "p1", "text": "hi"}
    record = ledger.remember(
        state=state,
        answers={"x": noul(0.2)},
        questions=["x"],
        model_version="scripted",
        policy_version="test",
        latency_ms=1,
    )
    ledger.consume(record["decision_id"], state, {"operation": "HOLD"})
    with pytest.raises(AlreadyConsumed):
        ledger.consume(record["decision_id"], state, {"operation": "HOLD"})
    other = DecisionLedger()
    fresh = other.remember(state=state, answers={}, questions=[], model_version="x", policy_version="y", latency_ms=0)
    with pytest.raises(StaleDecision):
        other.consume(fresh["decision_id"], {"packet_id": "p1", "text": "changed"}, {"operation": "HOLD"})


def test_gateway_returns_recommendations_and_refuses_forbidden_consume():
    provider = routing_script()
    gateway = SystemOneGateway(provider, policy_version="test")
    result = gateway.decide(
        {"goal": "Fix the selector"},
        policy_context={"domain": "routing", "goal": "Fix the selector"},
    )
    assert result["kind"] == "recommendation"
    assert result["consumed_at"] is None
    assert result["bound"]["operation"] == "RECOMMEND_ROUTE"
    assert result["bound"]["choice"] == "kimi_explore"
    with pytest.raises(ValueError, match="forbidden"):
        gateway.consume(result["decision_id"], result["bound"], {"kind": "declare_done"})
    observed = dict(AgentRoutingActionSpace().observe({"goal": "Fix the selector"}))
    consumed = gateway.consume(result["decision_id"], observed, {"operation": "RECOMMEND_ROUTE"})
    assert consumed["consumed_at"]
    with pytest.raises(AlreadyConsumed):
        gateway.consume(result["decision_id"], observed, {"operation": "RECOMMEND_ROUTE"})


def test_human_required_actions_ignore_jev():
    assert approval_required("delete")
    answers = {
        "routing.best_executor.v2": choice(["kimi_coder", "human", "park"], "kimi_coder"),
        "agent.should_wake.v1": noul(0.99),
    }
    route = route_recommendation({"choice": "kimi_coder"}, answers, action_kind="deploy")
    assert route["executor"] == "human" and route["human_required"] is True and route["jev_vote"] is None


def test_wake_gate_uses_the_should_wake_lock_not_a_global_cutoff():
    answers = {
        "routing.best_executor.v2": choice(
            question_set(["routing.best_executor.v2"])["routing.best_executor.v2"]["criteria"],
            "kimi_explore",
        ),
        "agent.should_wake.v1": noul(0.2),
        "task.human_review_recommended.v1": noul(0.1),
        "routing.task_class.v1": choice(
            question_set(["routing.task_class.v1"])["routing.task_class.v1"]["criteria"],
            "debugging",
        ),
    }
    route = route_recommendation(
        {"choice": "kimi_explore", "task_class": "debugging"}, answers, model_version="jev-latest"
    )
    assert route["executor"] == "park"


def test_calibration_rejects_a_magical_global_confidence_rule():
    with pytest.raises(ValueError, match="Global confidence"):
        CalibrationLock(
            {
                "question_id": "anything",
                "model_version": "jev-latest",
                "policy_version": "x",
                "threshold": {"kind": "global_confidence", "value": 0.85},
            }
        )
    lock = load_lock("routing.best_executor.v2")
    gated = apply_lock(
        lock, choice(["kimi_explore", "park"], "kimi_explore", confidence=0.1), model_version="jev-latest"
    )
    assert gated["accepted"] is False and gated["fallback"] == "park"


def test_brier_and_checked_in_locks_have_fixtures():
    assert brier_score([0.9, 0.1], [1, 0]) == pytest.approx(0.01)
    for path in LOCK_DIR.glob("*.json"):
        lock = json.loads(path.read_text())
        fixture = Path(__file__).resolve().parent.parent / lock["fixtures"]
        assert fixture.exists(), lock["question_id"]
        rows = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]
        assert len(rows) == lock["metrics"]["n_labeled"]


def test_completion_requires_evidence_and_never_sets_done():
    answers = {"completion.claim_supported.v3": noul(0.99)}
    empty = verify_completion("DONE", [], answers, lock=load_lock("completion.claim_supported.v3"))
    assert empty["closed"] is False and empty["jev_done"] is False
    receipts = [FileReceipt(path="fix.py", digest="abc"), Receipt("test", name="pytest", passed=True)]
    ok = verify_completion("null check added", receipts, answers, lock=load_lock("completion.claim_supported.v3"))
    assert ok["closed"] is True and ok["reason"] == "receipt_chain"
    blocked = verify_completion(
        "deployed", receipts, answers, action_kind="deploy", lock=load_lock("completion.claim_supported.v3")
    )
    assert blocked["closed"] is False and blocked["reason"] == "HUMAN REQUIRED"


def test_beowulf_does_not_call_jev_when_policy_already_requires_a_human():
    provider = routing_script()
    orchestrator = BeowulfOrchestrator(SystemOneGateway(provider))
    result = orchestrator.consider({"goal": "drop production"}, action_kind="delete")
    assert result["reason"] == "HUMAN REQUIRED"
    assert provider.calls == []


def test_pepper_executes_exactly_one_consumed_operation():
    space = ComputerActionSpace()
    observation = {
        "title": "Settings",
        "controls": [{"id": "save", "label": "Save", "operations": ["CLICK"]}],
    }
    observed = space.observe(observation)

    def answers(_state, asked):
        return {
            "operation": choice(asked["operation"]["criteria"], "CLICK"),
            "click_target": choice(asked["click_target"]["criteria"], "1"),
        }

    class Executor:
        def __init__(self):
            self.calls = []

        def execute_once(self, bound, text=None):
            self.calls.append((bound["operation"], bound["choice"], text))
            return {"clicked": bound["choice"]}

    executor = Executor()
    loop = PepperLoop(SystemOneGateway(ScriptedProvider(answers)), executor)
    first = loop.step(observation, "Save the toggle")
    assert first["executed"] is True and executor.calls == [("CLICK", "save", None)]
    with pytest.raises(AlreadyConsumed):
        loop.gateway.consume(
            first["decision_id"],
            dict(observed),
            {"operation": "CLICK", "target": "1"},
        )


def test_pepper_type_text_refuses_to_invent_strings():
    observation = {"controls": [{"id": "name", "label": "Name", "operations": ["TYPE_TEXT"]}]}

    def answers(_state, asked):
        return {
            "operation": choice(asked["operation"]["criteria"], "TYPE_TEXT"),
            "type_text_target": choice(asked["type_text_target"]["criteria"], "1"),
        }

    class Dummy:
        def execute_once(self, *_args, **_kwargs):
            return None

    loop = PepperLoop(SystemOneGateway(ScriptedProvider(answers)), executor=Dummy())
    with pytest.raises(ValueError, match="TYPE_TEXT needs Kimi"):
        loop.step(observation, "Enter the city")


def test_kimi_hook_is_fail_open_and_not_authority(tmp_path):
    code, stdout, receipt = handle(
        {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": str(tmp_path), "tool_input": {"command": "ls"}},
        receipt_dir=tmp_path,
    )
    assert code == 0
    assert stdout["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert receipt["authority"] == "none"
    assert receipt["looks_dangerous"] is False
    dangerous = handle(
        {"hook_event_name": "PreToolUse", "tool_input": {"command": "rm -rf /"}, "cwd": str(tmp_path)},
        receipt_dir=tmp_path,
    )
    assert dangerous[0] == 0 and dangerous[2]["looks_dangerous"] is True
    # Writing receipts onto a file path still exits 0 (fail-open).
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("x")
    code, _, _ = handle({"hook_event_name": "Stop", "cwd": str(tmp_path)}, receipt_dir=blocked)
    assert code == 0


def test_secrets_are_redacted_from_receipts_and_packets():
    packet = Packet(packet_id="p", identity="hexturtle", text="hi", receipts=[{"token": "abc"}])
    assert packet.redacted()["receipts"][0]["token"] == "***"
    assert redact({"TYPESAFE_API_KEY": "live-secret", "ok": 1})["TYPESAFE_API_KEY"] == "***"


def test_hierarchical_choice_consumes_only_the_selected_group():
    options = {f"agent_{i}": f"worker {i}" for i in range(40)}
    tree = hierarchical_choice(options, instructions="Pick a worker", group_size=10)
    assert tree["flat"] is False and "group" in tree["questions"]
    answers = {
        "group": choice(tree["questions"]["group"]["criteria"], "group_2"),
        "group_1": choice(tree["questions"]["group_1"]["criteria"], "agent_0"),
        "group_2": choice(tree["questions"]["group_2"]["criteria"], "agent_12"),
    }
    bound = bind_hierarchy(tree, answers)
    assert bound["choice"] == "agent_12" and bound["group"] == "group_2"


def test_replay_rejects_a_changed_state_hash():
    state = {"goal": "x"}
    record = {
        "decision_id": "d1",
        "state_hash": state_hash(state),
        "consumed_at": None,
        "requested_action": None,
        "result_receipt": None,
    }
    replayed = replay_decision(record, state, {"operation": "HOLD"})
    assert replayed["replayed"] is True
    with pytest.raises(StaleDecision):
        replay_decision(record, {"goal": "y"}, {"operation": "HOLD"})


def test_as_wire_accepts_question_lists():
    wire = as_wire([{"id": "q1", "type": "noul", "instructions": "Yes?"}])
    assert wire["q1"]["type"] == "noul"
    with pytest.raises(ValueError):
        choice_question({}, "empty")


def test_http_decision_endpoint_returns_recommendations_only(monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer

    import httpx

    import jev_ultrafast.adapters.gateway as gw

    port = 18767
    monkeypatch.setattr(gw, "PORT", port)
    monkeypatch.setattr(gw, "ORIGIN", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(gw, "TOKEN", "test-token")
    gw.GATEWAY = SystemOneGateway(routing_script(), policy_version="test")
    server = ThreadingHTTPServer(("127.0.0.1", port), gw.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        denied = httpx.post(
            f"http://127.0.0.1:{port}/decision",
            json={"state": {"goal": "x"}, "policy_context": {"domain": "routing"}},
            headers={"Host": f"127.0.0.1:{port}"},
        )
        assert denied.status_code == 403
        response = httpx.post(
            f"http://127.0.0.1:{port}/decision",
            json={
                "state": {"goal": "Fix the selector"},
                "policy_context": {"domain": "routing", "goal": "Fix the selector"},
            },
            headers={"X-Gateway-Token": "test-token", "Host": f"127.0.0.1:{port}"},
        )
        body = response.json()
        assert response.status_code == 200
        assert body["kind"] == "recommendation"
        assert body["consumed_at"] is None
        assert "declare_done" not in body
        assert body["bound"]["choice"] == "kimi_explore"
    finally:
        server.shutdown()
