"""Replay a decision log offline and check the consume-once invariants held."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ReplayReport:
    decisions: int = 0
    consumed: int = 0
    results: int = 0
    violations: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.violations

    def to_dict(self):
        return {**asdict(self), "ok": self.ok}


def replay_ledger(path):
    report = ReplayReport()
    issued, consumed, resulted = {}, set(), set()
    for number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        entry = json.loads(line)
        did, event = entry["decision_id"], entry["event"]
        if event == "issued":
            if did in issued:
                report.violations.append(f"line {number}: decision {did} issued twice")
            issued[did] = entry
            report.decisions += 1
        elif event == "consumed":
            if did not in issued:
                report.violations.append(f"line {number}: {did} consumed before it was issued")
            elif did in consumed:
                report.violations.append(f"line {number}: {did} consumed twice")
            elif entry["state_hash"] != issued[did]["state_hash"]:
                report.violations.append(f"line {number}: {did} consumed against a different state")
            elif entry.get("requested_action") is None:
                report.violations.append(f"line {number}: {did} consumed without a requested action")
            consumed.add(did)
            report.consumed += 1
        elif event == "result":
            if did not in consumed:
                report.violations.append(f"line {number}: {did} has a result but was never consumed")
            elif did in resulted:
                report.violations.append(f"line {number}: {did} has two results")
            resulted.add(did)
            report.results += 1
        else:
            report.violations.append(f"line {number}: unknown event {event!r}")
    return report
