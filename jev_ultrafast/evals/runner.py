"""Run labeled fixtures through a provider and measure each question ID.

Fixtures are gateway requests plus labels keyed by question ID. The runner reports accuracy and Brier score
for choices, Brier score and the best threshold for nouls, and mean absolute error for scores. A calibration
lock only becomes ``calibrated`` from a live or replayed provider with at least MIN_FIXTURES labels and a Brier
score better than chance. Dry runs with the label oracle only prove the pipeline and refresh fixture counts.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from ..adapters.beowulf import build_space
from ..core.calibration import CalibrationRecord, brier_score, choice_brier
from ..policy.rules import HERE as POLICY_DIR
from ..policy.rules import POLICY_VERSION
from ..providers import ReplayProvider, StubProvider, TypeSafeProvider

MIN_FIXTURES = 20
CHANCE_BRIER = 0.25
EVALS_DIR = Path(__file__).parent
THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 20)]


def load_fixtures(directory=EVALS_DIR, domains=None):
    fixtures = []
    for path in sorted(directory.glob("*/fixtures.jsonl")):
        if domains and path.parent.name not in domains:
            continue
        for line in path.read_text().splitlines():
            if line.strip():
                fixture = json.loads(line)
                fixture.setdefault("suite", path.parent.name)
                fixtures.append(fixture)
    return fixtures


def oracle_provider():
    """Answers straight from the labels. Proves the pipeline; must never produce a calibrated lock."""

    def answers(state, questions):
        labels = state.get("__labels__", {})
        result = {}
        for key, q in questions.items():
            label = labels.get(q.id)
            if q.type == "choice":
                options = list(q.criteria)
                pick = label if label in options else options[0]
                result[key] = {
                    "type": "choice",
                    "choice": pick,
                    "probabilities": {o: float(o == pick) for o in options},
                    "confidence": 1.0,
                }
            elif q.type == "score":
                level = int(label) if label is not None else 0
                keys = [str(i) for i in range(len(q.criteria))]
                result[key] = {
                    "type": "score",
                    "score": float(level),
                    "probabilities": {k: float(int(k) == level) for k in keys},
                    "confidence": 1.0,
                }
            else:
                result[key] = {"type": "noul", "noul": 1.0 if label else 0.0}
        return result

    return StubProvider(answers, model_version="oracle")


def run_fixtures(fixtures, provider, record=None):
    """Returns per-fixture results with validated answers and the questions that were asked."""
    results = []
    for fixture in fixtures:
        space = build_space(fixture["domain"], fixture["input"])
        state, questions = space.state(), space.questions()
        if provider.name == "stub":
            state = {**state, "__labels__": fixture["labels"]}
        evaluation = provider.evaluate(state, questions)
        if record is not None:
            record.record(state, questions, evaluation)
        answers = space.validate(evaluation.answers)
        recommendation = space.resolve(answers)
        results.append(
            {
                "id": fixture["id"],
                "suite": fixture["suite"],
                "labels": fixture["labels"],
                "answers": {questions[k].id: a for k, a in answers.items()},
                "types": {q.id: q.type for q in questions.values()},
                "recommendation": recommendation.to_dict(),
                "model_version": evaluation.model_version,
                "latency_ms": evaluation.latency_ms,
            }
        )
    return results


def summarize(results):
    per_question = defaultdict(lambda: {"n": 0, "predictions": [], "labels": [], "type": None})
    for r in results:
        for qid, label in r["labels"].items():
            answer = r["answers"].get(qid)
            if answer is None:
                continue
            bucket = per_question[qid]
            bucket["type"] = r["types"][qid]
            bucket["n"] += 1
            bucket["labels"].append(label)
            if bucket["type"] == "choice":
                bucket["predictions"].append(answer["probabilities"])
            elif bucket["type"] == "score":
                bucket["predictions"].append(answer["score"])
            else:
                bucket["predictions"].append(answer["noul"])
    summary = {}
    for qid, bucket in per_question.items():
        metrics = {"n": bucket["n"], "type": bucket["type"]}
        if bucket["type"] == "choice":
            metrics["brier"] = choice_brier(bucket["predictions"], bucket["labels"])
            metrics["accuracy"] = sum(
                max(p, key=p.get) == label for p, label in zip(bucket["predictions"], bucket["labels"], strict=True)
            ) / bucket["n"]
            metrics["threshold"] = None
        elif bucket["type"] == "score":
            errors = [abs(p - float(label)) for p, label in zip(bucket["predictions"], bucket["labels"], strict=True)]
            metrics["mean_absolute_error"] = sum(errors) / len(errors)
            metrics["brier"] = None
            metrics["threshold"] = None
        else:
            outcomes = [bool(label) for label in bucket["labels"]]
            metrics["brier"] = brier_score(bucket["predictions"], outcomes)
            best = max(
                THRESHOLDS,
                key=lambda t: (
                    sum((p >= t) == o for p, o in zip(bucket["predictions"], outcomes, strict=True)),
                    -abs(t - 0.5),
                ),
            )
            metrics["threshold"] = best
            metrics["accuracy"] = sum(
                (p >= best) == o for p, o in zip(bucket["predictions"], outcomes, strict=True)
            ) / bucket["n"]
        summary[qid] = metrics
    return summary


def calibration_records(summary, model_version, live):
    records = []
    for qid, m in summary.items():
        enough = m["n"] >= MIN_FIXTURES
        good = m.get("brier") is not None and m["brier"] < CHANCE_BRIER
        calibrated = live and enough and good and m["type"] != "score"
        notes = []
        if not live:
            notes.append("dry run with the label oracle; counts only")
        if not enough:
            notes.append(f"needs at least {MIN_FIXTURES} labeled fixtures, has {m['n']}")
        if live and m.get("brier") is not None and not good:
            notes.append(f"Brier {m['brier']:.3f} is not better than chance")
        if m["type"] == "score":
            notes.append("scores are consumed as values, not gated by a threshold")
        threshold = m.get("threshold") if m["type"] == "noul" else (0.5 if m["type"] == "choice" else None)
        records.append(
            CalibrationRecord(
                question_id=qid,
                model_version=model_version,
                policy_version=POLICY_VERSION,
                status="calibrated" if calibrated else "uncalibrated",
                fixtures=m["n"],
                threshold=threshold if calibrated else None,
                brier=m.get("brier") if live else None,
                accuracy=m.get("accuracy") if live else None,
                mean_absolute_error=m.get("mean_absolute_error") if live else None,
                measured_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) if live else None,
                notes="; ".join(notes),
            )
        )
    return records


def write_locks(records, directory=POLICY_DIR / "calibration_locks"):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for record in records:
        (directory / f"{record.question_id}.json").write_text(json.dumps(record.to_dict(), indent=2) + "\n")
    return sorted(directory.glob("*.json"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate labeled fixtures and refresh calibration locks.")
    parser.add_argument("--provider", choices=["oracle", "typesafe", "replay"], default="oracle")
    parser.add_argument("--suite", action="append", help="Limit to one or more suites (directory names).")
    parser.add_argument("--record", help="JSONL path to record live answers for later replay.")
    parser.add_argument("--replay", help="JSONL path of recorded answers for --provider replay.")
    parser.add_argument("--write-locks", action="store_true")
    args = parser.parse_args(argv)
    fixtures = load_fixtures(domains=args.suite)
    if args.provider == "typesafe":
        if not os.environ.get("TYPESAFE_API_KEY"):
            sys.exit("TYPESAFE_API_KEY is required for a live run. This costs money and is never run by tests.")
        provider = TypeSafeProvider()
    elif args.provider == "replay":
        provider = ReplayProvider(args.replay or "artifacts/eval-replay.jsonl")
    else:
        provider = oracle_provider()
    record = ReplayProvider(args.record) if args.record else None
    results = run_fixtures(fixtures, provider, record)
    summary = summarize(results)
    model_version = results[0]["model_version"] if results else provider.name
    live = args.provider != "oracle"
    records = calibration_records(summary, model_version, live)
    print(json.dumps({"fixtures": len(fixtures), "provider": provider.name, "summary": summary}, indent=2))
    if args.write_locks:
        for path in write_locks(records):
            print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
