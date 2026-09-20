"""Offline contracts for the reflex runtime. No paid APIs."""

import pytest

from jev_ultrafast.action_spaces.computer import ComputerActionSpace
from jev_ultrafast.action_spaces.relay import RelayActionSpace
from jev_ultrafast.action_spaces.repository import RepositoryActionSpace
from jev_ultrafast.action_spaces.router import AgentRoutingActionSpace
from jev_ultrafast.adapters import beowulf
from jev_ultrafast.adapters import kimi_acp as kimi
from jev_ultrafast.core import calibration, decision
from jev_ultrafast.evidence import Trace, receipt
from jev_ultrafast.gateway import SystemOneGateway
from jev_ultrafast.policy import requires_human, route


def answer(ids, selected):
    return {"choice": selected, "confidence": 0.9, "probabilities": {i: float(i == selected) for i in ids}}


def test_decision_consumed_once_against_exact_state():
    state = {"packets": [{"id": "p1"}]}
    record = decision.Decision(state, {"q": "a"}).to_record()
    decision.consume_once(record, {"packets": [{"id": "p1"}]})
    with pytest.raises(ValueError, match="already consumed"):
        decision.consume_once(record, {"packets": [{"id": "p1"}]})


def test_changed_state_invalidates_decision():
    record = decision.Decision({"a": 1}, {}).to_record()
    with pytest.raises(ValueError, match="State changed"):
        decision.consume_once(record, {"a": 2})


def test_calibration_registry_has_initial_question_set():
    for qid in (
        "relay.needs_reply.v1",
        "routing.best_executor.v2",
        "task.requires_browser.v1",
        "task.human_review_recommended.v4",
        "repo.change_risk.v2",
        "agent.should_wake.v1",
        "completion.claim_supported.v3",
    ):
        assert calibration.get_spec(qid).id == qid
    with pytest.raises(ValueError, match="No calibrated threshold"):
        calibration.apply_threshold("task.requires_browser.v1", 0.99)
    assert calibration.apply_threshold("relay.needs_reply.v1", 0.9) is True
    assert calibration.apply_threshold("relay.needs_reply.v1", 0.1) is False


def test_gateway_returns_recommendations_and_logs():
    questions = {
        "executor": {
            "question_id": "routing.best_executor.v2",
            "type": "choice",
            "criteria": {"kimi_explore": "Explore", "human": "Human"},
        }
    }

    def provider(_request):
        return {"model": "test", "answers": {"executor": answer(questions["executor"]["criteria"], "kimi_explore")}}

    gateway = SystemOneGateway(provider)
    result = gateway.decide({"task": "diagnose"}, questions, {"lane": "triage"})
    assert result["recommendations_only"] is True
    assert result["distributions"]["executor"]["kimi_explore"] == 1.0
    assert len(gateway.log()) == 1
    assert gateway.log()[0]["policy_context"] == {"lane": "triage"}


def test_gateway_rejects_unknown_question_id():
    gateway = SystemOneGateway(lambda _request: {"model": "t", "answers": {}})
    with pytest.raises(ValueError, match="Unknown question"):
        gateway.decide({}, {"q": {"question_id": "nope.v9", "criteria": {"a": "A"}}})


def test_policy_requires_human_for_authority_kinds():
    for kind in ("delete", "deploy", "money", "credential", "release"):
        assert requires_human(kind) is True
    assert requires_human("triage") is False
    routed = route("kimi_explore", action_kind="deploy", context={})
    assert routed == {
        "recommendation": "kimi_explore",
        "human_required": True,
        "dispatched_to": "human",
        "policy_version": "policy-v1",
    }
    assert route("pepper", action_kind="triage", context={})["dispatched_to"] == "pepper"


def test_completion_claim_is_recommendation_not_done():
    questions = {
        "claim": {
            "question_id": "completion.claim_supported.v3",
            "type": "choice",
            "criteria": {"yes": "Supported", "no": "Not supported"},
        }
    }

    def provider(_request):
        return {"model": "t", "answers": {"claim": answer(questions["claim"]["criteria"], "yes")}}

    result = SystemOneGateway(provider).decide({"evidence": ["tests"]}, questions)
    assert result["answers"]["claim"]["choice"] == "yes"
    assert result["recommendations_only"] is True


def test_action_spaces_map_to_observed_state_only():
    relay = RelayActionSpace().legal_actions({"packets": [{"id": "p1"}]})
    assert {a.operation for a in relay} == {
        "NOOP",
        "CLASSIFY",
        "SCORE",
        "RECOMMEND_ROUTE",
        "RECOMMEND_WAKE",
        "RECOMMEND_REPLY",
    }
    assert "SEND" not in {a.operation for a in relay}
    router = AgentRoutingActionSpace().legal_actions({"task": "fix"})
    assert {a.target for a in router} >= {"kimi_explore", "kimi_plan", "kimi_coder", "cursor", "pepper", "human"}
    repo = RepositoryActionSpace().legal_actions({"changes": [{"id": "c1"}]})
    assert repo and all(a.target == "c1" for a in repo)
    assert RepositoryActionSpace().legal_actions({"changes": []}) == []
    computer = ComputerActionSpace().legal_actions({"elements": [{"id": "e1", "label": "OK"}]})
    assert "click:e1" in {a.id for a in computer}


def test_receipt_chain_and_replay():
    state = {"packets": [{"id": "p1"}]}
    record = decision.Decision(state, {}).to_record()
    decision.consume_once(record, state)
    trace = Trace()
    event = receipt(
        decision_id=record["decision_id"], state_hash=record["state_hash"], requested_action="x"
    )
    trace.append({**event, "type": "executed"})
    assert trace.verify_chain() is True
    assert trace.replay(record, state)["decision_id"] == record["decision_id"]


def test_kimi_acp_frames_and_fail_open_hooks():
    session = kimi.acp_session_new(cwd="/tmp")
    assert session["method"] == "session/new"
    prompt = kimi.acp_prompt("s1", "diagnose", role="explore")
    assert prompt["params"]["role"] == "explore"
    with pytest.raises(ValueError, match="Unknown Kimi"):
        kimi.acp_prompt("s1", "x", role="giant")
    assert kimi.parse_message('{"jsonrpc":"2.0","method":"session/new","id":"1"}')["method"] == "session/new"
    with pytest.raises(ValueError, match="JSON-RPC"):
        kimi.parse_message("nope")
    assert kimi.emit_hook_receipt("PreToolUse", {"tool": "shell"})["fail_open"] is True
    assert kimi.emit_hook_receipt("Bogus")["degraded"] is True
    assert set(kimi.kimi_subagent_roles()) == {"explore", "plan", "coder"}


def test_beowulf_adapter_normalizes_and_gates():
    packet = beowulf.normalize_packet({"id": "p1", "identity": "hex", "text": "hi", "kind": "chat"})
    assert packet["packet_id"] == "p1"
    assert beowulf.recommend({}, "cursor", action_kind="release")["dispatched_to"] == "human"
