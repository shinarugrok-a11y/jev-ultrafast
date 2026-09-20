"""Relay domain. Recommendations only; Jev never sends a relay message.

Legal actions are judgments over observed packets: classify, score, recommend
a route or a wake, or do nothing. Transport, retries, and lane switches stay
in deterministic COMPSD/Beowulf code.
"""

from jev_ultrafast.core.action_space import ActionSpace, LegalAction

OPERATIONS = ("CLASSIFY", "SCORE", "RECOMMEND_ROUTE", "RECOMMEND_WAKE", "RECOMMEND_REPLY", "NOOP")


class RelayActionSpace(ActionSpace):
    name = "relay"
    operations = OPERATIONS

    def legal_actions(self, state):
        packets = state.get("packets", [])
        legal = [LegalAction(id="noop", operation="NOOP", target=None, label="No relay action recommended")]
        for packet in packets:
            pid = packet.get("id", "?")
            legal.append(LegalAction(id=f"classify:{pid}", operation="CLASSIFY", target=pid, label=f"Classify {pid}"))
            legal.append(LegalAction(id=f"score:{pid}", operation="SCORE", target=pid, label=f"Score {pid}"))
            legal.append(
                LegalAction(id=f"route:{pid}", operation="RECOMMEND_ROUTE", target=pid, label=f"Recommend route {pid}")
            )
            legal.append(
                LegalAction(id=f"wake:{pid}", operation="RECOMMEND_WAKE", target=pid, label=f"Recommend wake {pid}")
            )
            legal.append(
                LegalAction(id=f"reply:{pid}", operation="RECOMMEND_REPLY", target=pid, label=f"Recommend reply {pid}")
            )
        return legal
