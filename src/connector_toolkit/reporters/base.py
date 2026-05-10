from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import RunReport


class BaseReporter(ABC):
    """
    Abstract base for all output reporters.

    Implement `report()` to add a new output format.
    Register the subclass in runner.REPORTER_REGISTRY.

    Example
    -------
        class SlackReporter(BaseReporter):
            reporter_type = "slack"

            def report(self, run: RunReport) -> None:
                # post to webhook
                ...
    """

    reporter_type: str = ""

    @abstractmethod
    def report(self, run: RunReport) -> None:
        """Consume a completed RunReport and produce output."""
        ...
