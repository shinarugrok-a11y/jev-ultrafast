"""Action spaces expose legal operations and compatible targets. They never execute."""


class ObservedState(dict):
    """Indexed, domain-specific snapshot. Fingerprint lives on the dict."""


class BoundAction(dict):
    """A recommendation bound to observed elements. Authorization is not included."""


class ActionSpace:
    domain = "abstract"
    forbidden = ()

    def observe(self, raw_state):
        raise NotImplementedError

    def questions(self, observed, *, goal="", history=None, extra=None):
        raise NotImplementedError

    def bind(self, answers, observed):
        """Consume only the selected operation's compatible target."""
        raise NotImplementedError

    def fingerprint(self, observed):
        from ..core.decision import state_hash

        return observed.get("fingerprint") or state_hash(observed)
