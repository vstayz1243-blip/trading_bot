import math
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Runtime settings; order execution safety is intentionally locked."""

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout: float = 300.0
    ollama_max_concurrent: int = 1

    dry_run: Literal[True] = True
    demo_orders_enabled: Literal[False] = False

    def __post_init__(self) -> None:
        if not isinstance(self.ollama_base_url, str) or not self.ollama_base_url.strip():
            raise ValueError("ollama_base_url must be a non-empty string.")
        if not isinstance(self.ollama_model, str) or not self.ollama_model.strip():
            raise ValueError("ollama_model must be a non-empty string.")
        if (
            isinstance(self.ollama_timeout, bool)
            or not isinstance(self.ollama_timeout, (int, float))
            or not math.isfinite(self.ollama_timeout)
            or self.ollama_timeout <= 0
        ):
            raise ValueError("ollama_timeout must be positive and finite.")
        if (
            isinstance(self.ollama_max_concurrent, bool)
            or not isinstance(self.ollama_max_concurrent, int)
            or self.ollama_max_concurrent < 1
        ):
            raise ValueError("ollama_max_concurrent must be a positive integer.")
        if self.dry_run is not True:
            raise ValueError("dry_run is locked to True.")
        if self.demo_orders_enabled is not False:
            raise ValueError("demo_orders_enabled is locked to False.")


SETTINGS = RuntimeSettings()
