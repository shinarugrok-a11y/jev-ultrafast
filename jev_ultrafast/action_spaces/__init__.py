"""Pluggable action spaces. Jev selects; application code determines what is executable."""

from .agent_router import AgentRoutingActionSpace
from .base import ActionSpace, BoundAction, ObservedState
from .browser import BrowserActionSpace, index_actions
from .computer import ComputerActionSpace
from .relay import RelayActionSpace
from .repository import RepoActionSpace

SPACES = {
    "browser": BrowserActionSpace,
    "relay": RelayActionSpace,
    "routing": AgentRoutingActionSpace,
    "repository": RepoActionSpace,
    "computer": ComputerActionSpace,
}


def get_space(domain):
    if domain not in SPACES:
        raise KeyError(f"Unknown action space {domain!r}")
    return SPACES[domain]()


__all__ = [
    "ActionSpace",
    "AgentRoutingActionSpace",
    "BoundAction",
    "BrowserActionSpace",
    "ComputerActionSpace",
    "ObservedState",
    "RelayActionSpace",
    "RepoActionSpace",
    "SPACES",
    "get_space",
    "index_actions",
]
