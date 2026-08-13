class AgentBrainError(Exception):
    """Base error with a safe, user-facing message."""


class SecurityError(AgentBrainError):
    """Input was rejected before persistence."""

    def __init__(self, reasons: list[str]):
        self.reasons = sorted(set(reasons))
        super().__init__("input rejected: " + ", ".join(self.reasons))


class ValidationError(AgentBrainError):
    """Canonical content or configuration is invalid."""
