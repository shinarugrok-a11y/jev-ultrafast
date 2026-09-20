"""Jev chooses an observed action. Code owns execution.

The browser agent (``Agent``) is the original reflex and the regression fixture. Around it: ``core`` holds the
provider-independent contract, ``action_spaces`` bound each domain, ``policy`` holds authority, ``adapters``
connect Beowulf, COMPSD, Kimi Code, and Pepper, and ``evidence`` records what actually happened.
"""

from .agent import Agent
from .browser import Browser

__all__ = ["Agent", "Browser"]
