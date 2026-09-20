"""Bounded action spaces. Each one indexes what was observed, asks typed questions, and maps answers back."""

from .agent_router import AgentRoutingActionSpace
from .base import ActionSpace, Recommendation, evaluate_space
from .browser import BrowserActionSpace
from .computer import ComputerActionSpace, normalize_screen
from .relay import RelayActionSpace
from .repository import RepoActionSpace

__all__ = [
    "ActionSpace",
    "AgentRoutingActionSpace",
    "BrowserActionSpace",
    "ComputerActionSpace",
    "Recommendation",
    "RelayActionSpace",
    "RepoActionSpace",
    "evaluate_space",
    "normalize_screen",
]
