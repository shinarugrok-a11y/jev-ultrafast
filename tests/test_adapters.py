"""Pepper executes one approved operation, Kimi is driven over ACP with deterministic permissions, hooks observe."""

import io
import json
import sys
import textwrap

import pytest

from jev_ultrafast.adapters import CompsdRecorder, Job, KimiACP, PepperLoop, SystemOneGateway, WorkerPolicy
from jev_ultrafast.adapters.kimi_acp import hook_main, hook_receipt, run_job
from jev_ultrafast.core import AlreadyConsumed, CalibrationRecord, DecisionLedger
from jev_ultrafast.evidence import Receipt, TraceWriter, verify_chain
from jev_ultrafast.policy import Policy
from jev_ultrafast.providers import StubProvider

SCREEN = {
    "screen": {"app": "Browser", "title": "Vendor form", "text": "Company name  Submit"},
    "elements": [
        {"id": "el-1", "role": "textbox", "label": "Company name", "value": "", "bounds": [10, 10, 200, 30]},
        {"id": "el-2", "role": "button", "label": "Submit", "bounds": [10, 100, 80, 30]},
    ],
}


def computer_provider(operation, generation=0.1):
    def answers(_state, questions):
        out = {}
        for key, q in questions.items():
            if q.type == "choice":
                pick = operation if operation in q.criteria else list(q.criteria)[0]
                probabilities = {o: float(o == pick) for o in q.criteria}
                out[key] = {"choice": pick, "confidence": 0.95, "probabilities": probabilities}
            else:
                out[key] = {"noul": generation if key == "task.requires_generation.v1" else 0.05}
        return out

    return StubProvider(answers, model_version="jev-test")


def policy(calibrated=True):
    ids = ["task.human_review_recommended.v4", "computer.operation.v1"]
    status = "calibrated" if calibrated else "uncalibrated"
    threshold, brier = (0.5, 0.1) if calibrated else (None, None)
    locks = {qid: CalibrationRecord(qid, "jev-test", "p", status, 40, threshold, brier) for qid in ids}
    gates = {
        "flags": {"task.human_review_recommended.v4": {"trip_when": "above", "verdict": "review"}},
        "confidence": {"computer.operation.v1": {"verdict": "review"}},
    }
    return Policy(locks, gates)


def test_pepper_executes_exactly_one_approved_operation_and_consumes_first(tmp_path):
    executed = []
    gateway = SystemOneGateway(computer_provider("CLICK"), policy(), DecisionLedger(tmp_path / "log.jsonl"))
    loop = PepperLoop(gateway, lambda action: executed.append(action) or {"clicked": action["element_id"]})
    result = loop.step(SCREEN, "Submit the form")
    assert result.status == "executed" and result.operation == "CLICK"
    assert executed == [result.requested_action]
    assert result.requested_action["element_id"] == "el-2" and result.requested_action["bounds"] == [10, 100, 80, 30]
    assert result.receipt["result"] == {"clicked": "el-2"}
    decision = gateway.ledger.decisions[result.decision_id]
    assert decision.consumed_at is not None and decision.result_receipt is not None
    with pytest.raises(AlreadyConsumed):
        gateway.consume(result.decision_id, loop._state_for(SCREEN, "Submit the form", []), result.requested_action)


def test_pepper_records_execution_even_when_the_executor_raises_after_acting(tmp_path):
    gateway = SystemOneGateway(computer_provider("CLICK"), policy(), DecisionLedger(tmp_path / "log.jsonl"))

    def executor(_action):
        raise RuntimeError("screen went away after the click")

    loop = PepperLoop(gateway, executor)
    with pytest.raises(RuntimeError):
        loop.step(SCREEN, "Submit the form")
    decision = next(iter(gateway.ledger.decisions.values()))
    assert decision.consumed_at is not None and decision.result_receipt["executed"]["operation"] == "CLICK"


def test_pepper_wakes_kimi_for_text_instead_of_typing():
    executed = []
    gateway = SystemOneGateway(computer_provider("TYPE", generation=0.9), policy())
    result = PepperLoop(gateway, executed.append).step(SCREEN, "Fill in the company name")
    assert result.status == "wake_kimi" and executed == []
    assert result.requested_action["element_id"] == "el-1" and "text" not in result.requested_action
    assert result.requested_action["state_hash"]


@pytest.mark.parametrize(
    "operation, status", [("DONE", "claimed_done"), ("BLOCKED", "blocked"), ("REQUEST_HELP", "request_help")]
)
def test_pepper_terminal_operations_execute_nothing(operation, status):
    executed = []
    gateway = SystemOneGateway(computer_provider(operation), policy())
    result = PepperLoop(gateway, executed.append).step(SCREEN, "Submit the form")
    assert result.status == status and executed == []
    assert gateway.ledger.decisions[result.decision_id].consumed_at is None


def test_pepper_holds_when_policy_does_not_say_act():
    executed = []
    gateway = SystemOneGateway(computer_provider("CLICK"), policy(calibrated=False))
    result = PepperLoop(gateway, executed.append).step(SCREEN, "Submit the form")
    assert result.status == "held" and result.verdict == "review" and executed == []
    human = PepperLoop(gateway, executed.append).step(SCREEN, "Delete the account", categories=["delete"])
    assert human.verdict == "human_required" and executed == []


FAKE_ACP_SERVER = textwrap.dedent(
    """
    import json, sys
    def send(m):
        sys.stdout.write(json.dumps(m) + "\\n"); sys.stdout.flush()
    perm_options = [{"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                    {"optionId": "reject", "name": "Reject", "kind": "reject_once"}]
    prompt_id, chosen = None, []
    for line in sys.stdin:
        m = json.loads(line)
        method = m.get("method")
        if method == "initialize":
            assert m["params"]["clientCapabilities"]["terminal"] is False
            send({"jsonrpc": "2.0", "id": m["id"], "result": {"protocolVersion": 1,
                  "agentInfo": {"name": "Kimi Code CLI", "version": "test"}, "agentCapabilities": {}}})
        elif method == "session/new":
            send({"jsonrpc": "2.0", "id": m["id"], "result": {"sessionId": "sess-1", "modes": {}}})
        elif method == "session/prompt":
            prompt_id = m["id"]
            text = m["params"]["prompt"][0]["text"]
            send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "sess-1", "update": {
                  "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text.split()[2]}}}})
            send({"jsonrpc": "2.0", "id": 100, "method": "session/request_permission", "params": {
                  "sessionId": "sess-1", "toolCall": {"toolCallId": "t1", "title": "Edit file.py", "kind": "edit",
                  "rawInput": {"path": "file.py"}}, "options": perm_options}})
        elif "id" in m and m["id"] == 100:
            chosen.append(m["result"]["outcome"].get("optionId"))
            send({"jsonrpc": "2.0", "id": 101, "method": "session/request_permission", "params": {
                  "sessionId": "sess-1", "toolCall": {"toolCallId": "t2", "title": "Bash", "kind": "execute",
                  "rawInput": {"command": "rm -rf build/"}}, "options": perm_options}})
        elif "id" in m and m["id"] == 101:
            chosen.append(m["result"]["outcome"].get("optionId"))
            send({"jsonrpc": "2.0", "id": 102, "method": "fs/read_text_file", "params": {"path": "x"}})
        elif "id" in m and m["id"] == 102:
            assert "error" in m
            tail = " " + ",".join(chosen)
            send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "sess-1", "update": {
                  "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": tail}}}})
            send({"jsonrpc": "2.0", "id": prompt_id, "result": {"stopReason": "end_turn"}})
        elif method == "session/cancel":
            pass
    """
)


@pytest.mark.parametrize(
    "kind, expected",
    [("explore", "`explore` reject,reject"), ("plan", "`plan` reject,reject"), ("coder", "`coder` allow,reject")],
)
def test_kimi_acp_permissions_follow_the_worker_kind_and_never_approve_human_categories(tmp_path, kind, expected):
    job = Job(kind, "Map the world selector modules.", str(tmp_path))
    result = run_job(job, command=[sys.executable, "-c", FAKE_ACP_SERVER], timeout=20)
    assert result["stop_reason"] == "end_turn" and result["session_id"] == "sess-1"
    assert result["text"] == expected
    decisions = result["permissions"]
    assert [d["allowed"] for d in decisions] == [kind == "coder", False]
    assert decisions[1]["categories"] == ["delete"]


def test_job_prompt_names_the_subagent_and_rejects_unknown_workers(tmp_path):
    assert "`explore` sub-agent" in Job("explore", "Look around", str(tmp_path)).prompt()
    with pytest.raises(ValueError, match="Unknown Kimi worker"):
        Job("root", "anything", str(tmp_path))


def test_worker_policy_cancels_when_no_matching_option_exists(tmp_path):
    policy = WorkerPolicy(Job("coder", "x", str(tmp_path)))
    result, record = policy.decide({"kind": "edit"}, [{"optionId": "x", "kind": "unknown"}])
    assert result == {"outcome": {"outcome": "cancelled"}} and record["allowed"] is False


def test_kimi_client_does_not_start_a_process_until_asked(tmp_path):
    client = KimiACP(Job("plan", "x", str(tmp_path)))
    assert client.process is None
    client.close()


def test_hook_payloads_become_receipts_and_advisory_denials(tmp_path, monkeypatch):
    receipts = tmp_path / "receipts.jsonl"
    monkeypatch.setenv("JEV_RECEIPTS", str(receipts))
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s1",
        "tool_name": "Bash",
        "cwd": str(tmp_path),
        "tool_input": {"command": "git push origin main --force"},
    }
    out = io.StringIO()
    assert hook_main(io.StringIO(json.dumps(payload)), out) == 0
    advisory = json.loads(out.getvalue())
    assert advisory["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "advisory" in advisory["hookSpecificOutput"]["permissionDecisionReason"]
    recorded = json.loads(receipts.read_text().splitlines()[0])
    assert recorded["kind"] == "file" and recorded["evidence"]["categories"] == ["delete"]
    quiet = io.StringIO()
    assert hook_main(io.StringIO(json.dumps({"hook_event_name": "SubagentStop", "session_id": "s1"})), quiet) == 0
    assert quiet.getvalue() == ""
    assert hook_receipt({"hook_event_name": "SubagentStop", "session_id": "s1"}).kind == "transport"
    assert hook_main(io.StringIO("not json"), io.StringIO()) == 0


def test_compsd_recorder_refuses_duplicate_relay_ids(tmp_path):
    recorder = CompsdRecorder(tmp_path / "compsd.jsonl", identity="beowulf")
    first = recorder.record("transport", "task-1", relay_id="r-1", reply_to="m1")
    assert first.evidence["relay_id"] == "r-1" and recorder.seen("r-1")
    with pytest.raises(ValueError, match="already recorded"):
        recorder.record("transport", "task-1", relay_id="r-1")
    assert len(recorder.for_subject("task-1")) == 1
    assert json.loads((tmp_path / "compsd.jsonl").read_text())["issuer"] == "beowulf"


def test_receipt_chain_requires_independent_proof():
    chain = [
        Receipt("file", "task-1", "kimi_coder", at=1),
        Receipt("transport", "task-1", "relay", at=2),
        Receipt("ack", "task-1", "hexturtle", at=3),
    ]
    incomplete = verify_chain(chain, "task-1", claimant="kimi_coder")
    assert not incomplete.complete and incomplete.missing == ["proof"]
    self_proof = verify_chain([*chain, Receipt("proof", "task-1", "kimi_coder", at=4)], "task-1", "kimi_coder")
    assert not self_proof.complete and "issued by the claimant" in self_proof.problems[0]
    proven = verify_chain([*chain, Receipt("proof", "task-1", "pepper", at=4)], "task-1", "kimi_coder")
    assert proven.complete
    out_of_order = verify_chain([*chain, Receipt("proof", "task-1", "pepper", at=0)], "task-1", "kimi_coder")
    assert "out of order" in out_of_order.problems[0]
    with pytest.raises(ValueError, match="Unknown receipt kind"):
        Receipt("vibes", "task-1", "anyone")


def test_trace_writer_records_errors_and_nesting(tmp_path):
    writer = TraceWriter(tmp_path / "trace.jsonl")
    with writer.span("outer") as outer:
        with pytest.raises(RuntimeError):
            with writer.span("inner", parent=outer):
                raise RuntimeError("boom")
    spans = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]
    assert [s["name"] for s in spans] == ["inner", "outer"]
    assert spans[0]["status"] == "error" and spans[0]["parent_span_id"] == spans[1]["span_id"]
    assert spans[0]["events"][0]["message"] == "boom" and spans[1]["status"] == "ok"
