"""Beowulf adapter. Normalize packets, ask Jev, apply deterministic policy."""

from jev_ultrafast.policy import route


def normalize_packet(packet):
    return {
        "packet_id": packet.get("id", "?"),
        "identity": packet.get("identity", "unknown"),
        "text": (packet.get("text", "") or "")[:2000],
        "kind": packet.get("kind", "unknown"),
    }


def recommend(state, recommendation, *, action_kind="unknown", context=None):
    """Policy-gated handback helper. Returns recommendation + human gate flag."""
    return route(recommendation, action_kind=action_kind, context=context or state.get("policy_context", {}))
