"""Every domain indexes observed candidates, fans out speculative heads, and consumes only the matching one."""

import pytest

from jev_ultrafast import model
from jev_ultrafast.action_spaces import (
    AgentRoutingActionSpace,
    BrowserActionSpace,
    ComputerActionSpace,
    RelayActionSpace,
    RepoActionSpace,
    evaluate_space,
    normalize_screen,
)
from jev_ultrafast.core import DecisionLedger, state_hash
from jev_ultrafast.providers import StubProvider


def choice(options, selected, confidence=0.9):
    return {"choice": selected, "confidence": confidence, "probabilities": {o: float(o == selected) for o in options}}


def score(levels, level):
    return {"score": float(level), "probabilities": {str(i): float(i == level) for i in range(levels)}, "confidence": 1}


THREAD = {
    "id": "t1",
    "messages": [
        {"id": "m1", "from": "hexturtle", "text": "Can you check the nightly build?", "at": "t0"},
        {"id": "m2", "from": "ci-bot", "text": "nightly: passed", "at": "t1"},
    ],
}


def relay_answers(operation, target="1", needs_reply=0.9):
    return {
        "relay.next_operation.v1": choice(["REPLY", "ACK", "FORWARD", "ESCALATE", "PARK", "IGNORE"], operation),
        "relay.reply_target.v1": choice(["1", "2"], target),
        "relay.needs_reply.v1": {"noul": needs_reply},
        "task.likely_duplicate_work.v1": {"noul": 0.05},
        "task.human_review_recommended.v4": {"noul": 0.1},
    }


def test_relay_reply_maps_to_an_observed_message_and_never_sends():
    space = RelayActionSpace(THREAD, "beowulf", recent_sends=[{"relay_id": "r1"}])
    assert space.state()["recent_sends"] == [{"relay_id": "r1"}]
    answers = space.validate(relay_answers("REPLY", "1"))
    rec = space.resolve(answers)
    assert rec.operation == "REPLY" and rec.target == "1" and rec.candidate["id"] == "m1"
    assert rec.authority == "recommendation"
    assert rec.flags["relay.needs_reply.v1"] == 0.9
    assert not hasattr(space, "send")


def test_relay_untargeted_operation_ignores_an_invalid_reply_head():
    space = RelayActionSpace(THREAD, "beowulf")
    answers = relay_answers("PARK")
    answers["relay.reply_target.v1"] = {"choice": "999"}
    rec = space.resolve(space.validate(answers))
    assert rec.operation == "PARK" and rec.target is None and rec.candidate is None


def test_relay_targeted_operation_rejects_an_unobserved_message():
    space = RelayActionSpace(THREAD, "beowulf")
    answers = relay_answers("ACK")
    answers["relay.reply_target.v1"] = choice(["1", "2", "3"], "3")
    with pytest.raises(ValueError, match="Invalid TypeSafe"):
        space.resolve(space.validate(answers))


def test_relay_rejects_unknown_operations_and_empty_threads():
    with pytest.raises(ValueError, match="Unsupported relay operations"):
        RelayActionSpace(THREAD, "beowulf", operations=["SEND_EVERYTHING"])
    with pytest.raises(ValueError, match="at least one observed message"):
        RelayActionSpace({"id": "t", "messages": []}, "beowulf")


def test_router_only_offers_available_executors():
    space = AgentRoutingActionSpace({"goal": "Fix the selector"}, ["kimi_explore", "human", "park"])
    q = space.questions()["routing.best_executor.v2"]
    assert set(q.criteria) == {"kimi_explore", "human", "park"}
    assert "agent.should_wake.v1" not in space.questions()
    with pytest.raises(ValueError, match="not part of this question"):
        AgentRoutingActionSpace({"goal": "x"}, ["chatgpt"])
    with pytest.raises(ValueError, match="at least one executor"):
        AgentRoutingActionSpace({"goal": "x"}, [])


def test_router_resolution_carries_class_scores_and_flags():
    space = AgentRoutingActionSpace({"goal": "Fix the selector"}, ["kimi_explore", "human"], sleeping_agent="kimi")
    questions = space.questions()
    answers = {"routing.best_executor.v2": choice(["kimi_explore", "human"], "kimi_explore")}
    for key, q in questions.items():
        if q.type == "choice" and key not in answers:
            answers[key] = choice(list(q.criteria), list(q.criteria)[3])
        elif q.type == "score":
            answers[key] = score(6, 2)
        elif q.type == "noul":
            answers[key] = {"noul": 0.7}
    rec = space.resolve(space.validate(answers))
    assert rec.operation == "ROUTE" and rec.target == "kimi_explore"
    assert rec.candidate["task_class"] == "coding"
    assert rec.scores["task.consequence.v1"] == 2 and rec.flags["agent.should_wake.v1"] == 0.7


def test_repository_focus_maps_to_an_observed_file():
    files = [{"path": "cli/receipts.py", "additions": 10}, {"path": "deploy/prod.yaml", "additions": 3}]
    space = RepoActionSpace("Add a flag", files, tests={"exit_code": 0}, branch="cursor/x")
    answers = {
        "repo.change_risk.v2": score(6, 4),
        "repo.riskiest_file.v1": choice(["1", "2"], "2"),
        "repo.change_matches_request.v1": {"noul": 0.2},
        "repo.tests_cover_change.v1": {"noul": 0.3},
        "task.human_review_recommended.v4": {"noul": 0.9},
    }
    rec = space.resolve(space.validate(answers))
    assert rec.candidate["path"] == "deploy/prod.yaml" and rec.scores["repo.change_risk.v2"] == 4
    with pytest.raises(ValueError, match="at least one changed file"):
        RepoActionSpace("x", [])


SCREEN = {
    "screen": {"app": "Browser", "title": "Vendor form", "text": "Company name  VAT id  Submit"},
    "elements": [
        {"id": "el-1", "role": "textbox", "label": "Company name", "value": "", "bounds": [10, 10, 200, 30]},
        {"id": "el-2", "role": "button", "label": "Submit", "bounds": [10, 100, 80, 30]},
        {"id": "el-3", "role": "heading", "label": "Vendor form", "bounds": [0, 0, 300, 20]},
        {"id": "el-4", "role": "button", "label": "No geometry"},
    ],
}


def test_normalizer_only_exposes_supported_elements_with_geometry():
    elements, targets = normalize_screen(SCREEN)
    assert [e["label"] for e in elements] == ["Company name", "Submit"]
    assert set(targets) == {"CLICK", "TYPE"}
    assert targets["TYPE"]["1"]["element_id"] == "el-1" and targets["CLICK"]["2"]["bounds"] == [10, 100, 80, 30]


def test_computer_click_cannot_consume_the_type_head_and_type_carries_no_text():
    space = ComputerActionSpace(SCREEN, "Fill in the company name")
    ops = list(space.operations)
    answers = {
        "computer.operation.v1": choice(ops, "CLICK"),
        "computer.click_target.v1": choice(["2"], "2"),
        "computer.type_target.v1": {"choice": "garbage"},
        "task.requires_generation.v1": {"noul": 0.1},
        "task.human_review_recommended.v4": {"noul": 0.1},
    }
    rec = space.resolve(space.validate(answers))
    assert rec.operation == "CLICK" and rec.candidate["element_id"] == "el-2"
    assert rec.candidate["bounds"] == [10, 100, 80, 30]
    answers["computer.operation.v1"] = choice(ops, "TYPE")
    answers["computer.type_target.v1"] = choice(["1"], "1")
    rec = space.resolve(space.validate(answers))
    assert rec.operation == "TYPE" and rec.candidate["element_id"] == "el-1"
    assert "text" not in rec.to_dict()["candidate"] and "text" not in rec.answers.get("computer.operation.v1", {})


def test_computer_without_editable_elements_does_not_offer_type():
    only_button = {"screen": {}, "elements": [{"id": "b", "role": "button", "label": "OK", "bounds": [0, 0, 1, 1]}]}
    space = ComputerActionSpace(only_button, "Press OK")
    assert "TYPE" not in space.operations and "computer.type_target.v1" not in space.questions()


def page():
    return {
        "url": "https://example.test/",
        "title": "Search",
        "text": "Search",
        "scroll": {"y": 0},
        "actions": [
            {"id": "e1", "kind": "fill", "label": "Search", "role": "textbox", "value": "", "node": 10},
            {"id": "e2", "kind": "click", "label": "Go", "role": "button", "value": "", "node": 20},
            {"id": "wait", "kind": "wait", "label": "Wait"},
        ],
    }


def test_browser_space_sends_the_original_request_unchanged():
    space = BrowserActionSpace(page(), "Find a book")
    body, *_ = model.browser_request(page(), "Find a book", [])
    assert space.state() == body["state"]
    assert {k: q.to_request() for k, q in space.questions().items()} == body["questions"]
    assert space.questions()["operation"].id == "browser.operation.v1"


def test_browser_space_consumes_only_the_matching_head():
    space = BrowserActionSpace(page(), "Find a book")
    operations = list(space.operations)
    answers = {
        "operation": choice(operations, "TYPE_TEXT"),
        "type_text_target": choice(["1"], "1"),
        "click_target": {"choice": "invented"},
    }
    rec = space.resolve(space.validate(answers))
    assert rec.operation == "TYPE_TEXT" and rec.candidate["id"] == "e1" and rec.answers["choice"] == "e1"
    answers["operation"] = choice(operations, "CLICK")
    with pytest.raises(ValueError, match="Invalid TypeSafe"):
        space.resolve(space.validate(answers))


def test_evaluate_space_issues_a_decision_bound_to_the_state_hash():
    space = RelayActionSpace(THREAD, "beowulf")
    provider = StubProvider(relay_answers("ACK", "2"), model_version="jev-test")
    ledger = DecisionLedger()
    rec, decision, evaluation = evaluate_space(space, provider, ledger)
    assert rec.candidate["id"] == "m2"
    assert decision.state_hash == state_hash(space.state()) and decision.model_version == "jev-test"
    assert "relay.reply_target.v1" in decision.question_ids and decision.consumed_at is None
    assert provider.calls[0]["questions"]["relay.next_operation.v1"]["type"] == "choice"
