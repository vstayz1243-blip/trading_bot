class ComputingError(Exception):
    """Base exception for computing-core failures."""


class TaskNotFoundError(ComputingError):
    """Raised when a task identifier is unknown."""


class TaskExecutionError(ComputingError):
    """Raised when a task cannot be dispatched to a worker."""


class ResourceLimitError(ComputingError):
    """Raised when configured resource limits prevent task execution."""


class ComputingShutdownError(ComputingError):
    """Raised when new work is submitted after shutdown has started."""
