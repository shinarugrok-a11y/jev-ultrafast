"""The Beowulf gateway returns recommendations, logs every decision, and never executes anything."""

import json
import threading

import httpx
import pytest

from jev_ultrafast.adapters.beowulf import SystemOneGateway, serve
from jev_ultrafast.core import AlreadyConsumed, CalibrationRecord, DecisionLedger, StaleDecision
from jev_ultrafast.evidence import TraceWriter, replay_ledger
from jev_ultrafast.policy import Policy
from jev_ultrafast.providers import StubProvider

THREAD = {"id": "t1", "messages": [{"id": "m1", "from": "hexturtle", "text": "Check the nightly build?", "at": "t0"}]}


def choice(options, selected, confidence=0.9):
    return {"choice": selected, "confidence": confidence, "probabilities": {o: float(o == selected) for o in options}}


def relay_provider(operation="REPLY"):
    def answers(_state, questions):
        out = {}
        for key, q in questions.items():
            if q.type == "choice":
                pick = operation if operation in q.criteria else list(q.criteria)[0]
                out[key] = choice(list(q.criteria), pick)
            elif q.type == "noul":
                out[key] = {"noul": 0.9 if key == "relay.needs_reply.v1" else 0.1}
            else:
                out[key] = {"score": 1.0, "probabilities": {str(i): float(i == 1) for i in range(len(q.criteria))},
                            "confidence": 1.0}
        return out

    return StubProvider(answers, model_version="jev-test")


def calibrated_policy():
    ids = [
        "task.human_review_recommended.v4",
        "task.likely_duplicate_work.v1",
        "relay.needs_reply.v1",
        "relay.next_operation.v1",
        "repo.change_matches_request.v1",
        "repo.tests_cover_change.v1",
        "repo.change_risk.v2",
        "completion.claim_supported.v3",
        "agent.should_wake.v1",
    ]
    locks = {qid: CalibrationRecord(qid, "jev-test", "policy.test", "calibrated", 40, 0.5, 0.1) for qid in ids}
    gates = json.loads((__import__("pathlib").Path("jev_ultrafast/policy/thresholds/gates.json")).read_text())
    return Policy(locks, gates)


def relay_request():
    return {"domain": "relay", "input": {"thread": THREAD, "identity": "beowulf"}, "policy_context": {}}


def test_decision_response_is_a_recommendation_with_provenance(tmp_path):
    gateway = SystemOneGateway(
        relay_provider(), calibrated_policy(), DecisionLedger(tmp_path / "log.jsonl"), TraceWriter(tmp_path / "t.jsonl")
    )
    response = gateway.decide(relay_request())
    assert response["authority"] == "recommendation"
    assert response["recommendation"]["operation"] == "REPLY" and response["recommendation"]["candidate"]["id"] == "m1"
    assert response["model_version"] == "jev-test" and response["policy"]["verdict"] == "act"
    assert response["distributions"]["relay.needs_reply.v1"] == {"true": 0.9, "false": pytest.approx(0.1)}
    assert set(response["calibration"].values()) <= {"calibrated", "none"}
    assert "sent" not in json.dumps(response) and "DONE" not in json.dumps(response["recommendation"])
    span = json.loads((tmp_path / "t.jsonl").read_text().splitlines()[0])
    assert span["attributes"]["jev.decision_id"] == response["decision_id"]
    assert span["attributes"]["policy.verdict"] == "act"


def test_consume_and_result_follow_the_ledger_rules(tmp_path):
    gateway = SystemOneGateway(relay_provider(), calibrated_policy(), DecisionLedger(tmp_path / "log.jsonl"))
    response = gateway.decide(relay_request())
    state = gateway.ledger.decisions[response["decision_id"]]
    from jev_ultrafast.action_spaces import RelayActionSpace

    current = RelayActionSpace(THREAD, "beowulf").state()
    assert state.state_hash == response["state_hash"]
    with pytest.raises(StaleDecision):
        gateway.consume(response["decision_id"], {**current, "identity": "someone-else"}, {"op": "REPLY"})
    gateway.consume(response["decision_id"], current, {"op": "REPLY", "target": "1"})
    with pytest.raises(AlreadyConsumed):
        gateway.consume(response["decision_id"], current, {"op": "REPLY", "target": "1"})
    gateway.result(response["decision_id"], {"kind": "transport", "relay_id": "r-9"})
    assert replay_ledger(tmp_path / "log.jsonl").ok


def test_questions_domain_answers_standard_questions_directly():
    gateway = SystemOneGateway(relay_provider(), calibrated_policy())
    response = gateway.decide(
        {
            "domain": "questions",
            "input": {"state": {"claim": "done", "evidence": {}}, "question_ids": ["completion.claim_supported.v3"]},
        }
    )
    assert response["recommendation"]["operation"] == "ANSWER"
    assert response["recommendation"]["flags"]["completion.claim_supported.v3"] == 0.1
    assert response["policy"]["verdict"] == "review"  # claim_supported below its threshold trips review
    with pytest.raises(ValueError, match="Unknown or empty"):
        gateway.decide({"domain": "questions", "input": {"state": {}, "question_ids": ["made.up.v1"]}})


def test_protected_paths_force_human_required_regardless_of_answers():
    gateway = SystemOneGateway(relay_provider(), calibrated_policy())
    response = gateway.decide(
        {
            "domain": "repository",
            "input": {"request": "Add flag", "files": [{"path": "cli/x.py"}, {"path": "deploy/prod.yaml"}]},
            "policy_context": {"protected_paths": {"deploy/*": "deploy"}},
        }
    )
    assert response["policy"]["verdict"] == "human_required"
    assert response["policy"]["reasons"][0].startswith("deploy:")


def test_unknown_domain_is_rejected():
    gateway = SystemOneGateway(relay_provider(), calibrated_policy())
    with pytest.raises(ValueError, match="Unknown decision domain"):
        gateway.decide({"domain": "email", "input": {}})


def test_loopback_http_surface_requires_token_and_serves_decisions(tmp_path):
    gateway = SystemOneGateway(relay_provider("PARK"), calibrated_policy(), DecisionLedger(tmp_path / "log.jsonl"))
    server = serve(gateway, 0, token="secret")
    port = server.server_address[1]
    host = f"127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://{host}"
        denied = httpx.post(f"{base}/decision", json=relay_request(), headers={"Host": host})
        assert denied.status_code == 403
        headers = {"Host": host, "X-Gateway-Token": "secret"}
        ok = httpx.post(f"{base}/decision", json=relay_request(), headers=headers)
        assert ok.status_code == 200 and ok.json()["recommendation"]["operation"] == "PARK"
        bad = httpx.post(f"{base}/decision", json={"domain": "nope"}, headers=headers)
        assert bad.status_code == 400 and "Unknown decision domain" in bad.json()["error"]
        missing = httpx.post(f"{base}/other", json={}, headers=headers)
        assert missing.status_code == 404
    finally:
        server.shutdown()
        server.server_close()
