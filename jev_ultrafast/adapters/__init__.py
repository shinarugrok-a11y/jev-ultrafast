"""Adapters to the rest of the network. Each one consumes recommendations; none of them grants authority."""

from .beowulf import SystemOneGateway
from .compsd import CompsdRecorder
from .kimi_acp import Job, KimiACP, WorkerPolicy, hook_receipt
from .pepper import PepperLoop

__all__ = ["CompsdRecorder", "Job", "KimiACP", "PepperLoop", "SystemOneGateway", "WorkerPolicy", "hook_receipt"]
