"""Versioned, runner-neutral contracts shared by platform and test runners."""

from testpilot.contracts.runner import (
    ContractError,
    ExecutionPolicy,
    RunManifest,
    RunResult,
    RunSelection,
)

__all__ = ["ContractError", "ExecutionPolicy", "RunManifest", "RunResult", "RunSelection"]
