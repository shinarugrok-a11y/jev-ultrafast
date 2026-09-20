"""Pluggable action spaces. Browser stays the regression fixture."""

from .base import ActionSpace, LegalAction
from .browser import BrowserActionSpace
from .computer import ComputerActionSpace
from .relay import RelayActionSpace
from .repository import RepositoryActionSpace
from .router import AgentRoutingActionSpace

__all__ = [
    "ActionSpace",
    "AgentRoutingActionSpace",
    "BrowserActionSpace",
    "ComputerActionSpace",
    "LegalAction",
    "RelayActionSpace",
    "RepositoryActionSpace",
]
