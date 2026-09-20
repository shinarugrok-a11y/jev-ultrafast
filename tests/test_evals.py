"""Fixtures, runner, and checked-in calibration locks stay consistent with each other. No paid APIs."""

import json
from pathlib import Path

import pytest

from jev_ultrafast.adapters.beowulf import build_space
from jev_ultrafast.evals import MIN_FIXTURES, load_fixtures, oracle_provider, run_fixtures, summarize, write_locks
from jev_ultrafast.evals.runner import calibration_records, main
from jev_ultrafast.policy.rules import HERE as POLICY_DIR

LOCKS = POLICY_DIR / "calibration_locks"


def test_every_fixture_builds_a_space_and_labels_only_asked_questions():
    fixtures = load_fixtures()
    assert {f["suite"] for f in fixtures} == {"agent_wake", "browser", "completion", "relay", "repository", "routing"}
    for fixture in fixtures:
        space = build_space(fixture["domain"], fixture["input"])
        asked = {q.id for q in space.questions().values()}
        unknown = set(fixture["labels"]) - asked
        assert not unknown, f"{fixture['id']} labels {unknown} that were never asked"


def test_oracle_run_is_perfect_and_never_calibrates():
    results = run_fixtures(load_fixtures(), oracle_provider())
    summary = summarize(results)
    assert all(m.get("accuracy", 1.0) == 1.0 for m in summary.values())
    for record in calibration_records(summary, "oracle", live=False):
        assert record.status == "uncalibrated" and record.brier is None and "dry run" in record.notes


def test_live_records_need_enough_fixtures_and_a_brier_better_than_chance():
    summary = {
        "a.small.v1": {"n": 5, "type": "noul", "brier": 0.05, "threshold": 0.6, "accuracy": 1.0},
        "a.enough.v1": {"n": MIN_FIXTURES, "type": "noul", "brier": 0.09, "threshold": 0.55, "accuracy": 0.9},
        "a.bad.v1": {"n": MIN_FIXTURES, "type": "noul", "brier": 0.3, "threshold": 0.5, "accuracy": 0.5},
        "a.choice.v1": {"n": MIN_FIXTURES, "type": "choice", "brier": 0.1, "threshold": None, "accuracy": 0.95},
        "a.score.v1": {"n": MIN_FIXTURES, "type": "score", "brier": None, "threshold": None},
    }
    summary["a.score.v1"]["mean_absolute_error"] = 0.4
    records = {r.question_id: r for r in calibration_records(summary, "jev-1.13.0", live=True)}
    assert records["a.small.v1"].status == "uncalibrated" and "at least" in records["a.small.v1"].notes
    assert records["a.enough.v1"].status == "calibrated" and records["a.enough.v1"].threshold == 0.55
    assert records["a.bad.v1"].status == "uncalibrated" and "not better than chance" in records["a.bad.v1"].notes
    assert records["a.choice.v1"].status == "calibrated" and records["a.choice.v1"].threshold == 0.5
    assert records["a.score.v1"].status == "uncalibrated" and records["a.score.v1"].mean_absolute_error == 0.4


def test_checked_in_locks_match_fixture_counts_and_are_honest():
    results = run_fixtures(load_fixtures(), oracle_provider())
    summary = summarize(results)
    files = {p.stem: json.loads(p.read_text()) for p in LOCKS.glob("*.json")}
    assert set(files) == set(summary), "run `uv run jev-eval --write-locks` after changing fixtures"
    for qid, record in files.items():
        assert record["question_id"] == qid and record["fixtures"] == summary[qid]["n"]
        if record["status"] == "calibrated":
            assert record["brier"] is not None and record["measured_at"] and record["model_version"] != "oracle"
        else:
            assert record["threshold"] is None


def test_runner_cli_dry_run_writes_locks_to_a_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("jev_ultrafast.evals.runner.write_locks", lambda records: write_locks(records, tmp_path))
    assert main(["--suite", "relay", "--write-locks"]) == 0
    written = sorted(p.name for p in tmp_path.glob("*.json"))
    assert "relay.next_operation.v1.json" in written and "routing.best_executor.v2.json" not in written
    out = capsys.readouterr().out
    assert '"provider": "stub"' in out


def test_live_runner_refuses_to_run_without_a_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="TYPESAFE_API_KEY"):
        main(["--provider", "typesafe"])


def test_replay_provider_round_trips_recorded_answers(tmp_path):
    from jev_ultrafast.providers import ReplayProvider

    fixtures = load_fixtures(domains=["agent_wake"])[:2]
    recorder = ReplayProvider(tmp_path / "replay.jsonl")
    run_fixtures(fixtures, oracle_provider(), record=recorder)
    replayed = ReplayProvider(tmp_path / "replay.jsonl")
    assert len(replayed.records) == 2
    space = build_space(fixtures[0]["domain"], fixtures[0]["input"])
    state = {**space.state(), "__labels__": fixtures[0]["labels"]}
    assert replayed.evaluate(state, space.questions()).answers["agent.should_wake.v1"]["noul"] == 1.0
    with pytest.raises(LookupError, match="No recorded answer"):
        replayed.evaluate({"other": 1}, space.questions())
    assert Path(tmp_path / "replay.jsonl").exists()
