"""Adapter surfaces. Transports stay outside the reflex runtime."""

from .kimi_acp import (
    HOOKS,
    acp_prompt,
    acp_session_new,
    emit_hook_receipt,
    kimi_subagent_roles,
    parse_message,
)

__all__ = [
    "HOOKS",
    "acp_prompt",
    "acp_session_new",
    "emit_hook_receipt",
    "kimi_subagent_roles",
    "parse_message",
]
